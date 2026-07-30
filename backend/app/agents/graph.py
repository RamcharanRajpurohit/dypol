"""Graph — the provider-agnostic LangGraph agent.

State machine:  START → prepare → agent → (tools → agent)* → END

  * ``prepare`` — trim history to the token budget and make the live system
    prompt (workspace + running summary) the first message.
  * ``agent``   — call the LLM. Provider/model fallback is handled INSIDE this
    node as a ``while`` loop over ``model_chain()``: a quota or hard error on
    provider/model N transparently retries N+1 in the SAME node invocation,
    preserving today's gemini→groq (and per-provider model-swap) behaviour.
    This in-node loop is intentional — it's simpler and far more testable than
    expressing cross-provider retries as graph edges, and keeps ``provider_idx``
    accurate so the next turn resumes where we left off.
  * ``tools``   — run the requested tools (with trace capture). At the tool-turn
    cap, inject a "synthesize now" nudge instead of running more tools.

The conditional edge from ``agent`` routes to ``tools`` while the last message
has tool calls and we're under the cap, else to END.
"""
from __future__ import annotations

import json
import re
import time
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from app.agents.memory import messages_from_mongo, trim_history
from app.agents.prompts import build_system_prompt
from app.agents.providers import (
    PROVIDER_REGISTRY,
    build_model,
    is_quota_error,
    model_chain,
)
from app.agents.trace import run_tools_with_trace
from app.core.config import get_settings


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    running_summary: str
    tool_trace: list[dict[str, Any]]
    provider_idx: int
    tool_turns: int
    empty_nudges: int  # how many times we've nudged the model out of an empty stall
    extra_context: str  # long-term user memory, appended to the system prompt


def build_agent_graph(
    tools: list[Any], install: dict[str, Any], collector: Any | None = None
):
    """Compile and return the LangGraph agent for one workspace + toolset.

    ``collector`` — optional shared ``TraceCollector`` so top-level tool rows
    and sub-agent (delegate) rows accumulate into one correctly-ordered flat
    list. When ``None`` the trace is returned via state only (no sub-agent
    interleaving), which is the path used by callers that don't delegate.
    """
    settings = get_settings()
    tools_by_name = {t.name: t for t in tools}
    chain = model_chain()

    async def prepare(state: AgentState) -> dict[str, Any]:
        """Trim history to the token budget and strip any stale system message.

        We deliberately do NOT inject the live system prompt here. ``add_messages``
        keys on message id and would re-append our fresh SystemMessage AFTER the
        re-supplied history objects (which keep their original ids), leaving the
        system prompt LAST — which Gemini then drops entirely. Instead the system
        prompt is prepended fresh inside the ``agent`` node at call time, so it's
        always first in what the model sees regardless of reducer identity quirks.
        """
        from langgraph.graph.message import RemoveMessage

        messages = list(state["messages"])
        non_system = [m for m in messages if not isinstance(m, SystemMessage)]
        keep = trim_history(non_system, settings.agent_history_token_budget)
        keep_ids = {id(m) for m in keep}
        # Remove anything not kept (trimmed-off history + any stale system msg).
        clears = [
            RemoveMessage(id=m.id)
            for m in messages
            if getattr(m, "id", None) and id(m) not in keep_ids
        ]
        return {"messages": clears} if clears else {}

    async def agent(state: AgentState) -> dict[str, Any]:
        """Invoke the LLM, falling back across ``model_chain()`` on error.

        The live system prompt (workspace context + running summary) is prepended
        here at call time so it is ALWAYS the first message the model receives.
        """
        system = SystemMessage(
            content=build_system_prompt(install, state.get("running_summary", ""))
            + state.get("extra_context", "")
        )
        history = [m for m in state["messages"] if not isinstance(m, SystemMessage)]
        messages = [system, *history]
        idx = state.get("provider_idx", 0)

        # On the FIRST turn, FORCE a tool call (tool_choice="any"). This is the
        # critical fix for Gemini 2.5-flash, which otherwise replies with text
        # (or narrates the tool call) instead of actually calling tools — the
        # cause of the "couldn't compose an answer" stalls and wrong answers.
        # After tools have run, switch to "auto" so the model can synthesize a
        # final text answer instead of being forced to keep calling tools.
        first_turn = state.get("tool_turns", 0) == 0
        tool_choice = "any" if first_turn else "auto"

        last_err: Exception | None = None
        while idx < len(chain):
            provider, use_fallback = chain[idx]
            try:
                model = build_model(
                    provider,
                    use_fallback=use_fallback,
                    tools=tools,
                    tool_choice=tool_choice,
                )
                start_ns = time.perf_counter_ns()
                resp = await model.ainvoke(messages)
                # An EMPTY response (no text AND no tool calls) is Gemini's
                # MALFORMED_FUNCTION_CALL pathology — a "successful" dud. On the
                # FIRST turn (where we forced a tool call) this means the model
                # failed to produce one, so treat it as a provider FAILURE and
                # advance the chain to a working model (e.g. flash → flash-lite),
                # instead of looping on the broken model and dead-ending.
                has_calls = bool(getattr(resp, "tool_calls", None))
                has_text = bool(_extract_text(resp).strip())
                if first_turn and not has_calls and not has_text:
                    last_err = RuntimeError("empty_response (malformed_function_call?)")
                    idx += 1
                    continue
                # Success — record which step we landed on for the next turn.
                _record_usage(collector, resp, provider, use_fallback, start_ns)
                return {"messages": [resp], "provider_idx": idx}
            except Exception as exc:  # quota OR hard error → try next step
                last_err = exc
                idx += 1
                continue

        # Every provider/model exhausted this turn — terminal, friendly message.
        reason = "quota" if (last_err and is_quota_error(last_err)) else "errors"
        text = (
            "All configured LLM providers are currently unavailable "
            f"({reason}). Please try again in a moment."
        )
        return {
            "messages": [AIMessage(content=text)],
            "provider_idx": max(len(chain) - 1, 0),
        }

    async def tools_node(state: AgentState) -> dict[str, Any]:
        """Run the last AIMessage's tool calls, capturing the trace."""
        last = state["messages"][-1]
        tool_calls = getattr(last, "tool_calls", None) or []
        turns = state.get("tool_turns", 0)

        tool_messages, trace = await run_tools_with_trace(
            tool_calls, tools_by_name, collector
        )
        # When a shared collector is in play it already holds the in-order flat
        # trace (top-level + nested sub-agent rows), so the state-level list is
        # not the source of truth; we still accumulate it for the no-collector
        # path. run_agent reads the collector when present, else state.
        return {
            "messages": tool_messages,
            "tool_trace": state.get("tool_trace", []) + trace,
            "tool_turns": turns + 1,
        }

    async def synthesize(state: AgentState) -> dict[str, Any]:
        """Final no-tools answer — reached at the tool-turn cap OR when the model
        stalled with an empty response.

        We re-ask WITHOUT tools so the model must compose an answer from the data
        already gathered. Critically, this tries EVERY provider in the chain until
        one returns non-empty text: Gemini occasionally returns an empty candidate
        for certain post-tool message sequences, and falling back to Groq (or the
        next provider) routes around that pathology instead of dead-ending.
        """
        system = SystemMessage(
            content=build_system_prompt(install, state.get("running_summary", ""))
            + state.get("extra_context", "")
        )
        nudge = SystemMessage(
            content=(
                "Do NOT call any tools. Using ONLY the data already gathered in "
                "this conversation (the tool results above), write the best, "
                "direct final answer to the user's question now. If the data is "
                "incomplete, answer with what you have and say what's missing. "
                "Never reply with an empty message or a greeting."
            )
        )
        history = [m for m in state["messages"] if not isinstance(m, SystemMessage)]
        convo = [system, *history, nudge]

        start = min(state.get("provider_idx", 0), max(len(chain) - 1, 0))
        # Try the current provider, then walk the rest of the chain on empty/error.
        order = list(range(start, len(chain))) + list(range(0, start))
        for idx in order:
            provider, use_fallback = chain[idx]
            try:
                model = build_model(provider, use_fallback=use_fallback)
                start_ns = time.perf_counter_ns()
                resp = await model.ainvoke(convo)
                _record_usage(collector, resp, provider, use_fallback, start_ns)
                text = _extract_text(resp).strip()
                # Empty OR a raw tool-payload echo → try the next provider
                # rather than persisting something the user can't read.
                if text and not _looks_like_tool_payload(text):
                    return {"messages": [resp]}
            except Exception:
                continue

        return {
            "messages": [
                AIMessage(
                    content=(
                        "I gathered some data but couldn't finish composing an "
                        "answer. Please try rephrasing the question."
                    )
                )
            ]
        }

    async def nudge(state: AgentState) -> dict[str, Any]:
        """Push the model out of an empty stall.

        Some models (notably Gemini) return an AIMessage with neither tool calls
        nor text — typically after an early, unnecessary ``workspace_info`` call.
        A mid-stream SystemMessage does NOT reliably move it; a HumanMessage
        (a fresh user turn) does. We bump a counter so a persistent stall falls
        through to the no-tools ``synthesize`` step instead of looping forever.
        """
        from langchain_core.messages import HumanMessage

        return {
            "messages": [
                HumanMessage(
                    content=(
                        "You stopped without answering. Call github_get now to "
                        "fetch the data needed (e.g. "
                        "/users/{login}/repos or /user/repos to list "
                        "repositories), then answer my question directly. Do not "
                        "greet me or repeat anything."
                    )
                )
            ],
            "empty_nudges": state.get("empty_nudges", 0) + 1,
        }

    def route_after_agent(state: AgentState) -> str:
        last = state["messages"][-1]
        has_calls = bool(getattr(last, "tool_calls", None))
        if has_calls:
            # Wants tools: run them under the cap, else force a final answer.
            if state.get("tool_turns", 0) < settings.agent_max_tool_turns:
                return "tools"
            return "synthesize"
        # No tool calls. If the message has no usable text, recover instead of
        # dead-ending: nudge once (as a user turn) to push it to act; if it's
        # STILL empty after a nudge, force a no-tools synthesis from whatever
        # tool data was already gathered.
        text = _extract_text(last).strip() if isinstance(last, AIMessage) else ""
        if not text:
            nudges = state.get("empty_nudges", 0)
            if nudges < 1:
                return "nudge"
            return "synthesize"
        return END

    graph = StateGraph(AgentState)
    graph.add_node("prepare", prepare)
    graph.add_node("agent", agent)
    graph.add_node("tools", tools_node)
    graph.add_node("synthesize", synthesize)
    graph.add_node("nudge", nudge)

    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "agent")
    graph.add_edge("nudge", "agent")
    graph.add_conditional_edges(
        "agent",
        route_after_agent,
        {
            "tools": "tools",
            "synthesize": "synthesize",
            "nudge": "nudge",
            END: END,
        },
    )
    graph.add_edge("tools", "agent")
    graph.add_edge("synthesize", END)

    return graph.compile()


# A model that echoes a tool result instead of answering. Gemini does this
# after a run of function calls: it emits the serialized FunctionResponse as
# TEXT, e.g. {"github_search_response": {"output": "{\"total_count\": 135 …
# That is a valid non-empty string, so every emptiness check passed and the
# raw payload was persisted and shown to the user as the answer.
_FN_RESPONSE_RE = re.compile(r'"\w+_response"\s*:\s*[\{"]')
_PAYLOAD_HINTS = ('"output"', '"total_count"', '"items"', '"_truncated"')


def _record_usage(
    collector: Any | None,
    resp: Any,
    provider: str,
    use_fallback: bool,
    start_ns: int,
) -> None:
    """Attribute one model call's tokens, latency and cost to the turn.

    Best-effort and fully guarded: telemetry must never be able to fail a
    user's turn. The model id is read off the response where the provider
    reports it, falling back to the configured id for the chain step we're on
    — pricing is per model, so a wrong id would silently mis-cost the turn.
    """
    if collector is None or not hasattr(collector, "record_model_call"):
        return
    try:
        from app.agents.usage import extract_usage, model_name_of

        spec = PROVIDER_REGISTRY.get(provider) or {}
        attr = spec.get("fallback_model_attr" if use_fallback else "model_attr")
        configured = getattr(get_settings(), attr, "") if attr else ""
        in_tok, out_tok = extract_usage(resp)
        collector.record_model_call(
            model=model_name_of(resp, fallback=configured),
            input_tokens=in_tok,
            output_tokens=out_tok,
            duration_ms=int((time.perf_counter_ns() - start_ns) / 1_000_000),
        )
    except Exception:
        pass


def _looks_like_tool_payload(text: str) -> bool:
    """True if ``text`` is a serialized tool result rather than an answer."""
    t = text.strip()
    if not t or t[0] not in "{[":
        return False  # prose, or a fenced code block — leave it alone
    head = t[:600]
    if _FN_RESPONSE_RE.search(head):
        return True
    try:
        json.loads(t)
        return True  # a whole JSON document is never a user-facing answer
    except ValueError:
        # Usually a payload clipped by the token limit — still not prose.
        return any(h in head for h in _PAYLOAD_HINTS)


def _extract_text(message: Any) -> str:
    """Pull final text out of an AIMessage whose content may be a block list."""
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") in (None, "text") and block.get("text"):
                    parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content)


def _build_turn(
    install: dict[str, Any],
    prior: list[Any],
    content: str,
    emit: Any,
    extra_context: str = "",
):
    """Shared setup for both run paths — returns (graph, collector, init_state).

    A single ``TraceCollector`` (+ ``DelegationBudget``) is threaded through the
    orchestrator's tool node AND the delegate tools so every call — top-level or
    nested — lands in one correctly-ordered flat trace. ``extra_context`` (the
    user's long-term memory) is appended to the system prompt every turn.
    """
    from langchain_core.messages import HumanMessage

    from app.agents.tracing import TraceCollector

    collector = TraceCollector(emit=emit)

    extra_tools: list[Any] = []
    try:
        from app.agents.budget import DelegationBudget
        from app.agents.registry import build_delegate_tools

        budget = DelegationBudget()
        extra_tools = (
            build_delegate_tools(install, budget=budget, trace=collector) or []
        )
    except Exception:
        extra_tools = []  # sub-agent layer absent → base toolset only

    from app.agents.tools import build_tools

    tools = build_tools(install, extra_tools=extra_tools)
    graph = build_agent_graph(tools, install, collector=collector)

    history = messages_from_mongo(prior)
    # Anti-parrot guard: tool-calling models (esp. Gemini) tend to COPY the last
    # assistant message instead of answering a follow-up. When there's prior
    # history, frame the new question explicitly as a fresh task that must be
    # answered with tools — this reliably breaks the echo loop. First-turn
    # questions (no history) are passed through unchanged.
    if history:
        user_content = (
            f"{content}\n\n"
            "[This is a NEW question — do not repeat or rephrase any previous "
            "answer or greeting. Treat it as a fresh task: call the appropriate "
            "tools to fetch the real data, then answer THIS question directly.]"
        )
    else:
        user_content = content

    init_state = {
        "messages": [*history, HumanMessage(content=user_content)],
        "running_summary": "",
        "tool_trace": [],
        "provider_idx": 0,
        "tool_turns": 0,
        "empty_nudges": 0,
        "extra_context": extra_context or "",
    }
    return graph, collector, init_state


def _final_text_from(result: dict[str, Any]) -> str:
    for msg in reversed(result["messages"]):
        if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
            text = _extract_text(msg)
            if text.strip() and not _looks_like_tool_payload(text):
                return text
    return (
        "I couldn't compose an answer. Try rephrasing or splitting the "
        "question into smaller parts."
    )


def _run_config(obs: dict[str, Any] | None) -> dict[str, Any]:
    """Build the LangGraph run config, including Langfuse callbacks/metadata
    when an observability context is supplied."""
    config: dict[str, Any] = {"recursion_limit": 50}
    if obs:
        try:
            from app.agents import observability

            callbacks = observability.get_callbacks(**obs)
            if callbacks:
                config["callbacks"] = callbacks
                config["metadata"] = observability.run_metadata(**obs)
        except Exception:
            pass
    return config


async def run_agent(
    install: dict[str, Any],
    prior: list[Any],
    content: str,
    *,
    emit: Any | None = None,
    extra_context: str = "",
    obs: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Run one agent turn (non-streaming). Returns ``(final_text, tool_trace)``.

    ``emit`` — optional callback fired per tool/sub-agent row as it's recorded.
    ``extra_context`` — long-term user memory appended to the system prompt.
    ``obs`` — optional {user_id, org, session_id} for Langfuse tracing.
    """
    graph, collector, init_state = _build_turn(
        install, prior, content, emit, extra_context
    )
    result = await graph.ainvoke(init_state, config=_run_config(obs))
    final_text = _final_text_from(result)
    trace = collector.as_chat_tool_calls() or result.get("tool_trace", [])
    return final_text, trace


async def stream_agent(
    install: dict[str, Any],
    prior: list[Any],
    content: str,
    *,
    emit: Any | None = None,
    token_emit: Any | None = None,
    extra_context: str = "",
    obs: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Run one agent turn with LIVE TOKEN STREAMING.

    Same as :func:`run_agent` but drives the graph via ``astream_events`` and
    fires ``token_emit(text_delta)`` for each chunk the model generates — so the
    answer "types out" in real time. ``emit`` still fires per tool/sub-agent row.
    Returns the final ``(text, trace)`` for persistence, identical to run_agent.

    Token deltas from the FINAL answer turn are what we stream. We avoid
    streaming tokens from intermediate tool-deciding turns (which are usually
    empty or just tool-call plumbing) by only forwarding non-empty text chunks;
    the frontend appends them to the live assistant bubble.
    """
    graph, collector, init_state = _build_turn(
        install, prior, content, emit, extra_context
    )

    run_config = _run_config(obs)

    # Use stream_mode=["messages", "values"] — the LIGHTWEIGHT streaming path.
    # ``astream_events(version="v2")`` was 10-28s slower per turn (it instruments
    # every internal event); this yields token chunks + the running state
    # directly with near-zero overhead (first token in ~1.4s vs ~13-30s).
    final_result: dict[str, Any] | None = None
    streamed_any = False
    try:
        from langchain_core.messages import AIMessageChunk

        async for mode, chunk in graph.astream(
            init_state, stream_mode=["messages", "values"], config=run_config
        ):
            if mode == "messages" and token_emit is not None:
                msg = chunk[0] if isinstance(chunk, tuple) else chunk
                # Only stream assistant text deltas (not tool/echo plumbing).
                if isinstance(msg, AIMessageChunk):
                    delta = _extract_text(msg)
                    if delta:
                        streamed_any = True
                        token_emit(delta)
            elif mode == "values" and isinstance(chunk, dict) and "messages" in chunk:
                final_result = chunk  # latest full state snapshot
    except Exception:
        final_result = None  # fall through to a safe re-invoke

    if final_result is None:
        final_result = await graph.ainvoke(init_state, config=run_config)

    final_text = _final_text_from(final_result)
    trace = collector.as_chat_tool_calls() or final_result.get("tool_trace", [])
    # If nothing streamed (provider didn't emit token chunks), emit the whole
    # answer once so the client still shows it appear.
    if not streamed_any and token_emit is not None and final_text:
        token_emit(final_text)
    return final_text, trace
