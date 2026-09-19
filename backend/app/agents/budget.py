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

import os
from dataclasses import dataclass, field

# Per-loop cap: the max number of tool-calling turns any single bounded loop
# (orchestrator step or sub-agent) will iterate before it must produce a final
# answer. Kept here so both the orchestrator and ``app/agents/base.py`` import
# one shared constant.
#
# Raised from 6 after a measured failure: a code-analysis sub-agent spent all
# six calls just walking directories (contents → src → src/lib → src/app →
# src/app/api), hit the cap before opening a single file, and reported "could
# not read" for a path that was readable the whole time. Six turns is enough to
# answer a metrics question and not enough to read code.
#
# This is the "reasoning effort" axis in FUTURE_PLAN §2.2 — a global constant
# applied identically to "how many PRs merged last week" and "why did the auth
# refactor break billing". Env-overridable so it can be swept per workload
# until a policy sets it per query.
MAX_TOOL_TURNS = int(os.environ.get("AGENT_SUBAGENT_MAX_TURNS", "12"))


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
    # Raised alongside MAX_TOOL_TURNS: a sub-agent allowed 12 turns cannot
    # actually use them if the shared pool runs dry at 24. This is the real
    # cost ceiling for a turn — every tool call is an API request and grows the
    # context the next model call pays for — so it is env-overridable and
    # deliberately not generous.
    global_tool_cap: int = int(os.environ.get("AGENT_GLOBAL_TOOL_CAP", "40"))
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
