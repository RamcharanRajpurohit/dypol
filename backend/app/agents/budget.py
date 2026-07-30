"""Delegation & tool budgets — the safety rails for the sub-agent layer.

The orchestrator (``app/agents/graph.py``) and every sub-agent share ONE
:class:`DelegationBudget` instance for the lifetime of a single user turn.
It bounds three things so a runaway model can't fan out forever:

  * **depth**  — how many delegation levels are allowed. We hard-cap at 1 by
    *construction* (sub-agents never receive ``delegate_*`` tools, so they
    physically cannot sub-delegate), but ``max_depth`` is recorded for
    documentation / future nesting.
  * **breadth** — ``max_delegations`` distinct sub-agent calls per turn, plus
    a ``_seen`` set so the model can't re-delegate the *same* task key in a
    loop.
  * **global tool cap** — ``global_tool_cap`` total tool executions across the
    orchestrator AND all sub-agents combined, so the whole turn stays cheap.

Every limit surfaces to the model as a **recoverable dict result** (e.g.
``{"error": "delegation_budget_exhausted", ...}``) — never as a raised
exception. The model reads the error and answers with what it already has.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Per-loop cap: the max number of tool-calling turns any single bounded loop
# (orchestrator step or sub-agent) will iterate before it must produce a final
# answer. Kept here so both the orchestrator and ``app/agents/base.py`` import
# one shared constant.
MAX_TOOL_TURNS = 6


@dataclass
class DelegationBudget:
    """Mutable per-turn budget shared across the orchestrator and sub-agents.

    All ``can_*`` checks are pure reads; the ``note_*`` methods mutate the
    counters. Callers MUST gate every delegation / tool call behind the
    matching ``can_*`` check and translate a ``False`` into a recoverable
    dict error rather than raising.
    """

    max_depth: int = 1
    max_delegations: int = 3
    global_tool_cap: int = 24
    delegations_used: int = 0
    tool_calls_used: int = 0
    _seen: set = field(default_factory=set)

    # ── delegation breadth ────────────────────────────────────────────
    def can_delegate(self, task_key: str) -> bool:
        """True iff another delegation is permitted for ``task_key``.

        Blocks when the breadth cap is hit OR when this exact task key has
        already been delegated this turn (prevents re-delegation loops).
        """
        if self.delegations_used >= self.max_delegations:
            return False
        return task_key not in self._seen

    def note_delegation(self, task_key: str) -> None:
        """Record that a delegation for ``task_key`` was started."""
        self.delegations_used += 1
        self._seen.add(task_key)

    # ── global tool budget ────────────────────────────────────────────
    def can_call_tool(self) -> bool:
        """True iff the shared global tool budget has room for one more call."""
        return self.tool_calls_used < self.global_tool_cap

    def note_tool_call(self) -> None:
        """Record that one tool execution was consumed (anywhere in the turn)."""
        self.tool_calls_used += 1
