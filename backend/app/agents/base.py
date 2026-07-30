"""base — the reusable bounded tool-calling loop shared by sub-agents.

:func:`run_bounded_loop` is the generalized form of the original
``_run_groq_agent`` hand-loop: give it a bound-able chat model, a list of
LangChain tools, a system prompt and a task, and it drives the model through
up to ``max_turns`` rounds of tool calling, recording every call into the
shared :class:`~app.agents.tracing.TraceCollector` and respecting the shared
:class:`~app.agents.budget.DelegationBudget`.

It is provider-agnostic (works on any ``init_chat_model`` result that supports
``.bind_tools``) and label-aware: pass ``label="code_analyst"`` and every tool
row is recorded as ``"code_analyst→{tool}"`` so nested sub-agent calls flatten
into the one flat trace the UI renders.
"""
from __future__ import annotations

import json
import time
from typing import Any

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import BaseTool

from app.agents.budget import MAX_TOOL_TURNS, DelegationBudget
from app.agents.prompts import build_now_block
from app.agents.tracing import TraceCollector


def _coerce_text(content: Any) -> str:
    """Flatten an LLM message ``content`` (str | list-of-parts) to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for blk in content:
            if isinstance(blk, str):
                parts.append(blk)
            elif isinstance(blk, dict):
                # langchain content blocks: {"type": "text", "text": "..."}
                if blk.get("type") == "text" and isinstance(blk.get("text"), str):
                    parts.append(blk["text"])
        return "".join(parts).strip()
    return str(content or "")


async def run_bounded_loop(
    *,
    model: Any,
    tools: list[BaseTool],
    system_prompt: str,
    user_task: str,
    budget: DelegationBudget,
    trace: TraceCollector,
    label: str | None,
    max_turns: int = MAX_TOOL_TURNS,
) -> str:
    """Drive ``model`` through a bounded tool-calling loop and return its text.

    Parameters
    ----------
    model:
        Any chat model supporting ``.bind_tools(tools)`` and async
        ``.ainvoke(messages)`` (e.g. an ``init_chat_model`` result).
    tools:
        The restricted toolset this loop may use. NEVER contains
        ``delegate_*`` tools for a sub-agent — that is what enforces depth=1.
    system_prompt / user_task:
        The role prompt and the concrete task to work on.
    budget:
        Shared per-turn budget; gates every tool execution via
        ``can_call_tool`` / ``note_tool_call``.
    trace:
        Shared flat trace; each executed tool is recorded with ``label`` so
        sub-agent calls flatten as ``"{label}→{tool}"``.
    label:
        The owning sub-agent's name, or ``None`` for top-level loops.
    max_turns:
        Per-loop cap on tool-calling rounds (defaults to ``MAX_TOOL_TURNS``).

    Returns
    -------
    str
        The model's final text answer (best-effort even if the turn budget or
        loop cap is exhausted before a clean stop).
    """
    by_name: dict[str, BaseTool] = {t.name: t for t in tools}
    messages: list[Any] = [
        # Every sub-agent gets today's date appended. They filter and reason
        # over timestamps ("recent PRs", "stale branches"), and a model with no
        # clock will otherwise anchor on its training cutoff.
        SystemMessage(content=system_prompt + build_now_block()),
        HumanMessage(content=user_task),
    ]
    bound = model.bind_tools(tools) if tools else model

    last_text = ""
    for _turn in range(max_turns):
        resp: AIMessage = await bound.ainvoke(messages)
        messages.append(resp)

        tool_calls = getattr(resp, "tool_calls", None) or []
        if not tool_calls:
            # No tools requested — this is the model's final answer.
            return _coerce_text(resp.content)

        # Remember the latest text content in case we run out of turns/budget
        # before the model produces a tool-free answer.
        txt = _coerce_text(resp.content)
        if txt:
            last_text = txt

        for call in tool_calls:
            name = call.get("name", "")
            args = call.get("args", {}) or {}
            call_id = call.get("id") or name

            # Global tool budget — surface exhaustion as a recoverable result
            # the model can read, never as an exception.
            if not budget.can_call_tool():
                result: Any = {
                    "error": "tool_budget_exhausted",
                    "hint": (
                        "The global tool-call budget for this turn is used up. "
                        "Answer now using the information already gathered."
                    ),
                }
                trace.record(name, args, "error: tool_budget_exhausted", 0, label=label)
                messages.append(
                    ToolMessage(
                        content=json.dumps(result, default=str),
                        tool_call_id=call_id,
                    )
                )
                continue

            tool = by_name.get(name)
            t0 = time.monotonic()
            if tool is None:
                result = {
                    "error": "unknown_tool",
                    "message": f"No tool named {name!r} is available here.",
                    "available": list(by_name.keys()),
                }
            else:
                try:
                    result = await tool.ainvoke(args)
                except Exception as exc:  # tool errors are recoverable
                    result = {"error": "tool_error", "message": str(exc)}
            duration_ms = int((time.monotonic() - t0) * 1000)

            budget.note_tool_call()

            # Lazy import keeps this module independent of chat_tools at import
            # time and reuses the single preview implementation.
            from app.services.chat_tools import _result_preview

            trace.record(name, args, _result_preview(result), duration_ms, label=label)
            messages.append(
                ToolMessage(
                    content=json.dumps(result, default=str),
                    tool_call_id=call_id,
                )
            )

    # Loop cap reached without a tool-free answer. Make one last attempt to
    # get a clean text answer; fall back to whatever text we last saw.
    try:
        final: AIMessage = await model.ainvoke(
            messages
            + [
                HumanMessage(
                    content=(
                        "Tool budget for this task is exhausted. Give your best "
                        "concise answer now using only the findings above. Do not "
                        "request any more tools."
                    )
                )
            ]
        )
        text = _coerce_text(final.content)
        if text:
            return text
    except Exception:
        pass
    return last_text or "I could not complete the analysis within the tool budget."
