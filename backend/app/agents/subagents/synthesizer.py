"""Synthesizer — the terminal step that composes the final grounded answer.

When the orchestrator delegated to one or more specialist sub-agents, it calls
:func:`synthesize` to weave their findings into a single, citation-preserving
answer to the user's question. The synthesizer has NO tools — it reasons only
over the supplied findings and the (already flattened) tool trace, so it can't
introduce ungrounded facts.
"""
from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.base import _coerce_text
from app.agents.prompts import build_now_block
from app.agents.subagent_prompts import SYNTHESIZER_PROMPT


async def synthesize(
    model: Any,
    question: str,
    findings_list: list[str],
    raw_trace: Any,
) -> str:
    """Compose the final answer from ``findings_list`` for ``question``.

    Parameters
    ----------
    model:
        Any chat model supporting async ``.ainvoke``.
    question:
        The user's original question.
    findings_list:
        Concise findings returned by the sub-agents (one string each).
    raw_trace:
        The shared trace — either a :class:`~app.agents.tracing.TraceCollector`
        or an already-flattened ``list[dict]``. Used only as light grounding
        context (which tools ran); never the source of facts.

    Returns
    -------
    str
        The final grounded answer, ready to store/stream to the user.
    """
    if not findings_list:
        # Nothing to synthesize — let the caller fall back to a direct answer.
        return ""

    findings_block = "\n\n".join(
        f"[Finding {i + 1}]\n{f.strip()}"
        for i, f in enumerate(findings_list)
        if f and f.strip()
    )

    # Normalise the trace to a flat list of tool names for light context.
    calls: list[dict[str, Any]]
    if hasattr(raw_trace, "as_chat_tool_calls"):
        calls = raw_trace.as_chat_tool_calls()
    elif isinstance(raw_trace, list):
        calls = raw_trace
    else:
        calls = []
    tool_names = [c.get("name") for c in calls if isinstance(c, dict)]
    trace_hint = (
        "Tools used during research: " + ", ".join(str(n) for n in tool_names)
        if tool_names
        else "No tools were used."
    )

    user = (
        f"User question:\n{question}\n\n"
        f"Findings from specialist sub-agents:\n{findings_block}\n\n"
        f"{trace_hint}\n\n"
        "Write the final answer now: direct, concise, grounded ONLY in the "
        "findings above, preserving their citations."
    )

    resp = await model.ainvoke(
        [
            # Date block appended so the final answer can express
            # timestamps as "3 days ago" instead of raw ISO strings.
            SystemMessage(content=SYNTHESIZER_PROMPT + build_now_block()),
            HumanMessage(content=user),
        ]
    )
    text = _coerce_text(resp.content)
    if text:
        return text
    # Last-ditch fallback: stitch the findings together so the user still gets
    # something grounded even if the model returned empty.
    return "\n\n".join(findings_list)
