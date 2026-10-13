"""Per-turn resource policy — FUTURE_PLAN §6 / §8 Phase 2.

Every agent turn spends along four axes: which **model** tier answers, how much
**effort** it may spend (provider reasoning effort + tool-turn cap), how much
**memory** it sees (history budget + retrieval depth), and which **tools** are
bound. Today each axis is a constant spread across ``providers.py``,
``budget.py``, ``memory.py`` and settings. This package puts all four behind
one :class:`~app.policy.decision.PolicyDecision`, produced once per turn by a
:class:`~app.policy.baselines.Policy`, so that:

* the hand-tuned behaviour becomes an explicit, reproducible baseline
  (:class:`~app.policy.baselines.RoleTablePolicy` — the default, a pure
  refactor of today), and
* alternative policies (always-cheap, always-strong, a feature-driven router,
  and later the learned bandit) can be swapped in with ``AGENT_POLICY`` and
  compared on the same traces.

Modules:
  * ``decision`` — the ``PolicyDecision`` value object and the axis enums.
  * ``features`` — cheap, LLM-free difficulty features (the context vector).
  * ``effort``   — ordinal effort ladder → per-provider request parameters.
  * ``axes``     — applying a decision: chain ordering, tool scoping.
  * ``baselines``— the four baseline policies the plan requires.
  * ``registry`` — policy selection by name + the ``decide()`` entry point.
"""
from __future__ import annotations

from app.policy.decision import EffortLevel, ModelTier, PolicyDecision, ToolScope
from app.policy.registry import decide, get_policy

__all__ = [
    "EffortLevel",
    "ModelTier",
    "PolicyDecision",
    "ToolScope",
    "decide",
    "get_policy",
]
