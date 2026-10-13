"""The baseline policies FUTURE_PLAN §7 requires every result to report.

1. :class:`RoleTablePolicy` — **today's hand-tuned behaviour**, reproduced
   exactly. This is the default and the expert control arm; a refactor that
   changes its output changes production behaviour.
2. :class:`AlwaysStrongPolicy` — quality ceiling, cost ceiling.
3. :class:`AlwaysCheapPolicy` — cost floor.
4. :class:`HeuristicRouterPolicy` — a RouteLLM-style router: one scalar
   difficulty score from the features, thresholded into cheap vs strong, plus
   per-question-type settings for the other three axes.

A policy is anything with ``name`` and ``decide(ctx) -> PolicyDecision``. It
must be pure and fast — it runs before every turn, on the request path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.policy.axes import SHORT_HISTORY_TOKENS, history_budget, retrieval_k
from app.policy.decision import (
    EffortLevel,
    HistoryDepth,
    ModelTier,
    PolicyDecision,
    RetrievalDepth,
    ToolScope,
)
from app.policy.effort import tool_turns_for
from app.policy.features import TurnFeatures


@dataclass(frozen=True, slots=True)
class PolicyContext:
    """Everything a policy may look at. Configured values come from settings
    so a policy that wants "today's value" can return it without importing
    settings itself (which keeps policies trivially testable)."""

    features: TurnFeatures
    configured_tool_turns: int = 6
    configured_history_tokens: int = 12_000
    role: str = "orchestrator"
    extra: dict[str, Any] = field(default_factory=dict)


class Policy(Protocol):
    name: str

    def decide(self, ctx: PolicyContext) -> PolicyDecision: ...


def _base(ctx: PolicyContext, name: str) -> PolicyDecision:
    """Today's values on every axis — the starting point other policies edit."""
    return PolicyDecision(
        model_tier=ModelTier.STRONG,
        effort=EffortLevel.DEFAULT,
        max_tool_turns=ctx.configured_tool_turns,
        history=HistoryDepth.FULL,
        history_token_budget=ctx.configured_history_tokens,
        retrieval=RetrievalDepth.DEFAULT,
        retrieval_k=None,
        tool_scope=ToolScope.ALL,
        policy=name,
        features=ctx.features.as_dict(),
    )


class RoleTablePolicy:
    """Today's behaviour, as a policy.

    The orchestrator always starts on the strong model with every tool bound,
    the configured tool-turn cap, the full history budget and the default
    retrieval depth; sub-agent tiers stay in ``providers._ROLE_POLICY``. The
    decision ignores the query entirely — which is precisely the property
    §2.2 identifies and the learned policy is meant to improve on.
    """

    name = "role_table"

    def decide(self, ctx: PolicyContext) -> PolicyDecision:
        return _base(ctx, self.name).with_reason("static role table (current behaviour)")


class AlwaysStrongPolicy:
    """Strong model, high effort, everything on: the quality/cost ceiling."""

    name = "always_strong"

    def decide(self, ctx: PolicyContext) -> PolicyDecision:
        return PolicyDecision(
            model_tier=ModelTier.STRONG,
            effort=EffortLevel.HIGH,
            max_tool_turns=tool_turns_for(EffortLevel.HIGH, ctx.configured_tool_turns),
            history=HistoryDepth.FULL,
            history_token_budget=ctx.configured_history_tokens,
            retrieval=RetrievalDepth.LARGE,
            retrieval_k=retrieval_k(RetrievalDepth.LARGE),
            tool_scope=ToolScope.ALL,
            policy=self.name,
            reason="ceiling baseline",
            features=ctx.features.as_dict(),
        )


class AlwaysCheapPolicy:
    """Cheap model, minimal effort, core tools, short memory: the cost floor."""

    name = "always_cheap"

    def decide(self, ctx: PolicyContext) -> PolicyDecision:
        return PolicyDecision(
            model_tier=ModelTier.CHEAP,
            effort=EffortLevel.LOW,
            max_tool_turns=tool_turns_for(EffortLevel.LOW, ctx.configured_tool_turns),
            history=HistoryDepth.SHORT,
            history_token_budget=min(SHORT_HISTORY_TOKENS, ctx.configured_history_tokens),
            retrieval=RetrievalDepth.SMALL,
            retrieval_k=retrieval_k(RetrievalDepth.SMALL),
            tool_scope=ToolScope.CORE,
            policy=self.name,
            reason="floor baseline",
            features=ctx.features.as_dict(),
        )


# Weights for the router's difficulty score. Hand-set, positive = harder.
# These are the *prior* a learned policy starts from, not a claim of
# optimality; the eval harness will report how far off they are.
ROUTER_WEIGHTS: dict[str, float] = {
    "approx_tokens": 0.004,   # long questions tend to be compound
    "has_code": 0.30,
    "file_paths": 0.15,
    "identifiers": 0.06,
    "pr_refs": 0.05,
    "type_code": 0.35,
    "type_web": 0.10,
    "type_metric": -0.15,
    "type_smalltalk": -0.60,
    "topical_continuity": 0.10,
    "log_workspace_repos": 0.05,
}
ROUTER_BIAS = 0.20


def difficulty_score(features: TurnFeatures, weights: dict[str, float] | None = None) -> float:
    """Linear difficulty score clipped to [0, 1]."""
    w = weights or ROUTER_WEIGHTS
    raw = features.as_dict()
    score = ROUTER_BIAS + sum(w.get(k, 0.0) * float(v) for k, v in raw.items())
    return max(0.0, min(1.0, score))


class HeuristicRouterPolicy:
    """RouteLLM-style threshold router over the difficulty score.

    * score ≥ ``threshold`` → strong tier; otherwise cheap.
    * Effort scales with the score (low / medium / high).
    * Question type picks the tool scope: smalltalk needs no extended tools,
      metric questions are answered from GitHub data (core + delegates for the
      PR analyst), code and web questions get everything.
    * History follows topical continuity: a fresh topic gets SHORT memory, a
      follow-up keeps the FULL budget.
    """

    name = "heuristic_router"

    def __init__(self, threshold: float = 0.5, weights: dict[str, float] | None = None):
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be within [0, 1]")
        self.threshold = threshold
        self.weights = dict(weights or ROUTER_WEIGHTS)

    def decide(self, ctx: PolicyContext) -> PolicyDecision:
        f = ctx.features
        score = difficulty_score(f, self.weights)
        qtype = f.question_type

        tier = ModelTier.STRONG if score >= self.threshold else ModelTier.CHEAP
        if score >= 0.75:
            effort = EffortLevel.HIGH
        elif score >= 0.4:
            effort = EffortLevel.MEDIUM
        else:
            effort = EffortLevel.LOW

        if qtype == "smalltalk":
            scope, retrieval = ToolScope.CORE, RetrievalDepth.NONE
            effort, tier = EffortLevel.NONE, ModelTier.CHEAP
        elif qtype == "metric":
            scope, retrieval = ToolScope.DELEGATES, RetrievalDepth.SMALL
        else:
            scope = ToolScope.ALL
            retrieval = RetrievalDepth.LARGE if qtype == "code" else RetrievalDepth.DEFAULT

        follow_up = f.history_turns > 0 and f.topical_continuity >= 0.2
        history = HistoryDepth.FULL if follow_up else HistoryDepth.SHORT
        budget = history_budget(history, ctx.configured_history_tokens)
        return PolicyDecision(
            model_tier=tier,
            effort=effort,
            max_tool_turns=tool_turns_for(effort, ctx.configured_tool_turns),
            history=history,
            history_token_budget=budget,
            retrieval=retrieval,
            retrieval_k=retrieval_k(retrieval),
            tool_scope=scope,
            policy=self.name,
            reason=f"{qtype} question, difficulty {score:.2f} (threshold {self.threshold:.2f})",
            features={**f.as_dict(), "difficulty": round(score, 4)},
        )


BASELINES: dict[str, type] = {
    RoleTablePolicy.name: RoleTablePolicy,
    AlwaysStrongPolicy.name: AlwaysStrongPolicy,
    AlwaysCheapPolicy.name: AlwaysCheapPolicy,
    HeuristicRouterPolicy.name: HeuristicRouterPolicy,
}
