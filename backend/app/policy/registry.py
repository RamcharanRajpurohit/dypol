"""Policy selection and the per-turn ``decide()`` entry point.

``AGENT_POLICY`` picks the active policy by name (default ``role_table``,
i.e. today's behaviour). ``decide()`` is the one call the agent graph makes:
featurise → policy → clamp, with a hard guarantee that **a policy bug can never
fail a user's turn** — any exception in featurisation or in the policy falls
back to the role-table decision and is logged, not raised.
"""
from __future__ import annotations

import logging
from typing import Any

from app.policy.baselines import BASELINES, PolicyContext, RoleTablePolicy
from app.policy.decision import PolicyDecision
from app.policy.features import TurnFeatures, featurize

log = logging.getLogger("dypol.policy")

DEFAULT_POLICY = RoleTablePolicy.name


def available_policies() -> list[str]:
    return sorted(BASELINES)


def get_policy(name: str | None = None) -> Any:
    """Instantiate the policy called ``name`` (or the configured one).

    An unknown name logs a warning and returns the default rather than
    raising: a typo in an env var must degrade to current behaviour, not take
    chat down.
    """
    if name is None:
        name = _configured_name()
    key = (name or DEFAULT_POLICY).strip().lower()
    cls = BASELINES.get(key)
    if cls is None:
        log.warning(
            "policy: unknown AGENT_POLICY %r, using %s (known: %s)",
            name, DEFAULT_POLICY, ", ".join(available_policies()),
        )
        cls = BASELINES[DEFAULT_POLICY]
    return cls()


def _configured_name() -> str:
    try:
        from app.core.config import get_settings

        return getattr(get_settings(), "agent_policy", DEFAULT_POLICY) or DEFAULT_POLICY
    except Exception:
        return DEFAULT_POLICY


def _configured_limits() -> tuple[int, int]:
    """``(tool_turns, history_tokens)`` from settings, with today's defaults
    if settings can't be read (e.g. in an isolated unit test)."""
    try:
        from app.core.config import get_settings

        s = get_settings()
        return int(s.agent_max_tool_turns), int(s.agent_history_token_budget)
    except Exception:
        return 6, 12_000


def decide(
    question: str,
    prior: list[Any] | None = None,
    install: dict[str, Any] | None = None,
    *,
    policy: Any | None = None,
    role: str = "orchestrator",
) -> PolicyDecision:
    """Produce the clamped :class:`PolicyDecision` for one turn."""
    turns, history = _configured_limits()
    try:
        features = featurize(question, prior, install)
    except Exception as exc:  # featurisation must never block a turn
        log.warning("policy: featurize failed, using empty features: %s", exc)
        features = TurnFeatures()

    ctx = PolicyContext(
        features=features,
        configured_tool_turns=turns,
        configured_history_tokens=history,
        role=role,
    )
    active = policy if policy is not None else get_policy()
    try:
        decision = active.decide(ctx)
        if not isinstance(decision, PolicyDecision):
            raise TypeError(f"{type(active).__name__}.decide returned {type(decision).__name__}")
    except Exception as exc:
        log.warning("policy: %s failed, falling back to %s: %s",
                    getattr(active, "name", active), DEFAULT_POLICY, exc)
        decision = RoleTablePolicy().decide(ctx).with_reason(
            f"fallback after {getattr(active, 'name', 'policy')} error"
        )
    return decision.clamped()
