"""Trace — custom tool executor that records the ChatToolCall trace.

LangGraph ships a prebuilt ``ToolNode``, but it doesn't give us the
per-call ``{name, args, result_preview, duration_ms}`` records the frontend
renders as the collapsible "Used N tools" trace. So we run the tools
ourselves: this executor produces both the ``ToolMessage``s the model needs
(to continue reasoning) AND the flat trace dicts that map 1:1 onto the
``ChatToolCall`` schema (a hard frontend contract).

The ``result_preview`` is produced by ``_result_preview`` from
``app.services.chat_tools`` so the legacy loop and this LangGraph tracer
render identical previews.
"""
from __future__ import annotations

import json
import time
from typing import Any

from langchain_core.messages import ToolMessage

from app.services.chat_tools import _result_preview

# Cap a single tool payload handed back to the model — mirrors the legacy
# loop's 8k cap so we stay well under tight free-tier TPM budgets.
_MAX_TOOL_PAYLOAD = 8_000


async def run_tools_with_trace(
    tool_calls: list[dict[str, Any]],
    tools_by_name: dict[str, Any],
    collector: Any | None = None,
) -> tuple[list[ToolMessage], list[dict[str, Any]]]:
    """Execute each requested tool call, returning ``(messages, trace)``.

    ``tool_calls`` — the ``.tool_calls`` from an AIMessage; each item has
    ``name``, ``args`` (dict), and ``id``. For each: look up the tool by
    name (``{"error": "unknown_tool:..."}`` if missing), ``await`` it
    (capturing exceptions as ``{"error": str(exc)}``), and time it.

    ``collector`` — optional ``TraceCollector``. When given, each *plain*
    top-level call is recorded into it (no label → plain row), so the single
    shared collector holds the whole turn's trace in order. ``delegate_*`` tools
    are SKIPPED here on purpose: the delegate coroutine (``registry.py``) records
    its own visible parent row first and then its sub-agent's nested
    ``"{label}→tool"`` rows, all into the same collector — so by the time
    ``tool.ainvoke`` for a delegate returns, those rows are already present and
    correctly ordered. Double-recording here would duplicate the parent row.

    Returns:
      * ``messages`` — one ``ToolMessage`` per call (JSON-encoded result,
        capped, with the matching ``tool_call_id`` and ``name``).
      * ``trace``    — one flat dict per call shaped like ``ChatToolCall``
        (returned for callers not using a collector; identical content).
    """
    messages: list[ToolMessage] = []
    trace: list[dict[str, Any]] = []

    for call in tool_calls:
        name = call.get("name", "")
        args = call.get("args") or {}
        call_id = call.get("id", "")
        # delegate_* tools self-record (parent + nested rows) into the
        # collector, so we must not record them here too.
        is_delegate = name.startswith("delegate_")

        t0 = time.time()
        tool = tools_by_name.get(name)
        if tool is None:
            result: Any = {"error": f"unknown_tool:{name}"}
        else:
            try:
                result = await tool.ainvoke(args)
            except Exception as exc:  # tool runtime failure — keep the loop alive
                result = {"error": str(exc)}
        duration_ms = int((time.time() - t0) * 1000)
        preview = _result_preview(result)

        # Wrap UNTRUSTED external content (web/file/search results) in a trust
        # boundary + injection scan before handing it to the model — defense in
        # depth against indirect prompt injection. Trusted/structured results
        # (repo metadata, PR lists) pass through untouched. Errors pass through.
        try:
            from app.agents.guardrails import is_untrusted, wrap_untrusted

            if (
                not (isinstance(result, dict) and "error" in result)
                and is_untrusted(name, args)
            ):
                result = wrap_untrusted(result)
        except Exception:
            pass

        payload = json.dumps(result, default=str)[:_MAX_TOOL_PAYLOAD]
        messages.append(
            ToolMessage(content=payload, tool_call_id=call_id, name=name)
        )
        entry = {
            "name": name,
            "args": args,
            "result_preview": preview,
            "duration_ms": duration_ms,
        }
        trace.append(entry)
        # Record plain (non-delegate) top-level rows into the shared collector.
        # Delegate rows were already recorded above (pre-run) to fix ordering.
        if collector is not None and not is_delegate:
            collector.record(name, args, preview, duration_ms)

    return messages, trace
