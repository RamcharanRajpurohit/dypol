"""TraceCollector — the single flat tool-call trace for a whole turn.

The frontend renders a turn's tool usage as a flat list of
:class:`~app.models.schemas.ChatToolCall` rows (``name``, ``args``,
``result_preview``, ``duration_ms``). Sub-agents would naturally produce a
*tree* of calls, but the schema is a hard contract — so instead of nesting we
**flatten** every nested call back into the one flat list using a name-prefix
convention:

    orchestrator tool   →  "github_get"
    sub-agent tool      →  "code_analyst→github_get"
    the delegate row    →  "delegate_code_analyst"

One ``TraceCollector`` is created per user turn and threaded through the
orchestrator and *every* sub-agent, so the resulting list is already in the
exact flat shape the UI expects — zero schema or frontend change.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

# An optional sink for live streaming (future SSE): called with each
# ChatToolCall-shaped dict as it is recorded. Signature kept loose on purpose.
EmitCallback = Callable[[dict[str, Any]], None]


class TraceCollector:
    """Accumulates ChatToolCall-shaped dicts in one flat list.

    Thread a single instance through the orchestrator and all sub-agents.
    Sub-agent loops pass their ``label`` (the sub-agent name) so their tool
    rows get the ``"{label}→{tool}"`` prefix; top-level calls pass no label.
    """

    def __init__(self, emit: EmitCallback | None = None) -> None:
        self._calls: list[dict[str, Any]] = []
        # Stored for future SSE streaming — when set, fired on every record().
        self._emit = emit
        # Model calls are tracked separately from tool calls: tokens (and
        # therefore cost) accrue on LLM invocations, not on tool executions.
        # FUTURE_PLAN §2.4 lists the absence of this as the reason there is no
        # reward to train a policy on.
        self._model_calls: list[dict[str, Any]] = []

    def record(
        self,
        name: str,
        args: dict[str, Any] | None,
        result_preview: str | None,
        duration_ms: int | None,
        label: str | None = None,
    ) -> None:
        """Append one tool call to the flat trace.

        ``label`` — when given (a sub-agent's name), the recorded ``name``
        becomes ``f"{label}→{name}"`` so nested calls flatten under their
        owning sub-agent in the UI. Top-level (orchestrator) calls omit it.
        """
        entry: dict[str, Any] = {
            "name": f"{label}→{name}" if label else name,
            "args": args or {},
            "result_preview": result_preview,
            "duration_ms": duration_ms,
        }
        self._calls.append(entry)
        if self._emit is not None:
            try:
                self._emit(entry)
            except Exception:
                # Tracing must never break the turn — a faulty SSE sink is
                # swallowed silently.
                pass

    def record_model_call(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        duration_ms: int | None = None,
        label: str | None = None,
    ) -> None:
        """Record one LLM invocation with its token usage and dollar cost.

        This is the per-turn reward signal: ``reward = quality − λ·cost −
        μ·latency`` (FUTURE_PLAN §6) needs a real ``cost_usd``, and until now
        nothing produced one. Kept separate from the tool trace because the
        frontend's ``ChatToolCall`` shape is a hard contract.
        """
        from app.telemetry.cost import estimate

        c = estimate(model, input_tokens, output_tokens)
        self._model_calls.append(
            {
                "model": model,
                "label": label,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": c.usd,
                "priced": c.priced,
                "duration_ms": duration_ms,
            }
        )

    def as_chat_tool_calls(self) -> list[dict[str, Any]]:
        """Return the flat list of ChatToolCall-shaped dicts (live reference)."""
        return self._calls

    def model_calls(self) -> list[dict[str, Any]]:
        """Per-model-call usage rows (live reference)."""
        return self._model_calls

    def usage_summary(self) -> dict[str, Any]:
        """Turn-level totals — what a policy is scored on.

        ``fully_priced`` is False when any model call had no known rate, so a
        consumer can tell "this turn cost $0.004" from "this turn cost at
        least $0.004 and we couldn't price the rest".
        """
        return {
            "model_calls": len(self._model_calls),
            "tool_calls": len(self._calls),
            "input_tokens": sum(m["input_tokens"] for m in self._model_calls),
            "output_tokens": sum(m["output_tokens"] for m in self._model_calls),
            "cost_usd": round(
                sum(m["cost_usd"] or 0.0 for m in self._model_calls), 8
            ),
            "fully_priced": all(m["priced"] for m in self._model_calls),
            "latency_ms": sum(m["duration_ms"] or 0 for m in self._model_calls),
        }

    def __len__(self) -> int:  # convenience for callers / tests
        return len(self._calls)
