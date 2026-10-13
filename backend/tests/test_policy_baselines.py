"""The four baselines, and the registry that selects between them.

``RoleTablePolicy`` gets characterization tests: it IS current production
behaviour, so any drift here is a behaviour change, not a refactor.
"""

from __future__ import annotations

import pytest

from app.policy import registry
from app.policy.baselines import (
    BASELINES,
    AlwaysCheapPolicy,
    AlwaysStrongPolicy,
    HeuristicRouterPolicy,
    PolicyContext,
    RoleTablePolicy,
    difficulty_score,
)
from app.policy.decision import (
    EffortLevel,
    HistoryDepth,
    ModelTier,
    PolicyDecision,
    RetrievalDepth,
    ToolScope,
)
from app.policy.features import featurize


def _ctx(question: str, prior=None, turns: int = 6, history: int = 12_000) -> PolicyContext:
    return PolicyContext(
        features=featurize(question, prior),
        configured_tool_turns=turns,
        configured_history_tokens=history,
    )


QUESTIONS = [
    "hi",
    "How many PRs merged last week?",
    "Why did the auth refactor in backend/app/auth/deps.py break billing?",
    "What's in the latest Next.js changelog?",
]


# ── role_table: today's behaviour ────────────────────────────────────
@pytest.mark.parametrize("question", QUESTIONS)
def test_role_table_ignores_the_query(question):
    d = RoleTablePolicy().decide(_ctx(question))
    assert (d.model_tier, d.effort, d.tool_scope, d.history, d.retrieval) == (
        ModelTier.STRONG,
        EffortLevel.DEFAULT,
        ToolScope.ALL,
        HistoryDepth.FULL,
        RetrievalDepth.DEFAULT,
    )


def test_role_table_passes_configured_limits_through_unchanged():
    d = RoleTablePolicy().decide(_ctx("anything", turns=9, history=20_000))
    assert d.max_tool_turns == 9
    assert d.history_token_budget == 20_000
    assert d.retrieval_k is None
    assert d.policy == "role_table"


def test_role_table_records_features_for_replay():
    d = RoleTablePolicy().decide(_ctx("How many PRs merged last week?"))
    assert d.features["type_metric"] == 1.0


# ── ceiling and floor ────────────────────────────────────────────────
def test_always_strong_is_the_ceiling():
    d = AlwaysStrongPolicy().decide(_ctx("hi"))
    assert d.model_tier is ModelTier.STRONG
    assert d.effort is EffortLevel.HIGH
    assert d.tool_scope is ToolScope.ALL
    assert d.max_tool_turns >= 12


def test_always_cheap_is_the_floor():
    d = AlwaysCheapPolicy().decide(_ctx(QUESTIONS[2]))
    assert d.model_tier is ModelTier.CHEAP
    assert d.effort is EffortLevel.LOW
    assert d.tool_scope is ToolScope.CORE
    assert d.history is HistoryDepth.SHORT
    assert d.history_token_budget <= 3_000


def test_floor_spends_no_more_than_ceiling_on_every_axis():
    for q in QUESTIONS:
        lo = AlwaysCheapPolicy().decide(_ctx(q))
        hi = AlwaysStrongPolicy().decide(_ctx(q))
        assert lo.max_tool_turns <= hi.max_tool_turns
        assert lo.history_token_budget <= hi.history_token_budget
        assert lo.effort.rank <= hi.effort.rank


# ── heuristic router ─────────────────────────────────────────────────
def test_difficulty_score_is_bounded():
    for q in [*QUESTIONS, "x" * 20_000, ""]:
        s = difficulty_score(featurize(q))
        assert 0.0 <= s <= 1.0


def test_code_questions_score_harder_than_metric_questions():
    code = difficulty_score(featurize(QUESTIONS[2]))
    metric = difficulty_score(featurize(QUESTIONS[1]))
    assert code > metric


def test_router_sends_smalltalk_to_the_cheapest_setting():
    d = HeuristicRouterPolicy().decide(_ctx("hi"))
    assert d.model_tier is ModelTier.CHEAP
    assert d.effort is EffortLevel.NONE
    assert d.tool_scope is ToolScope.CORE
    assert d.retrieval is RetrievalDepth.NONE


def test_router_sends_code_questions_to_strong_with_everything():
    d = HeuristicRouterPolicy().decide(_ctx(QUESTIONS[2]))
    assert d.model_tier is ModelTier.STRONG
    assert d.tool_scope is ToolScope.ALL
    assert d.retrieval is RetrievalDepth.LARGE


def test_router_gives_metric_questions_core_plus_delegates():
    d = HeuristicRouterPolicy().decide(_ctx(QUESTIONS[1]))
    assert d.tool_scope is ToolScope.DELEGATES


def test_router_keeps_full_history_only_for_follow_ups():
    prior = [
        {"role": "user", "content": "how many PRs merged last week in api"},
        {"role": "assistant", "content": "12"},
    ]
    follow_up = HeuristicRouterPolicy().decide(
        _ctx("how many merged in api the week before?", prior)
    )
    fresh = HeuristicRouterPolicy().decide(_ctx("who owns the billing service?", prior))
    assert follow_up.history is HistoryDepth.FULL
    assert fresh.history is HistoryDepth.SHORT


def test_router_threshold_moves_the_tier():
    q = QUESTIONS[1]
    assert HeuristicRouterPolicy(threshold=0.0).decide(_ctx(q)).model_tier is ModelTier.STRONG
    assert HeuristicRouterPolicy(threshold=1.0).decide(_ctx(q)).model_tier is ModelTier.CHEAP


def test_router_rejects_an_out_of_range_threshold():
    with pytest.raises(ValueError):
        HeuristicRouterPolicy(threshold=1.5)


def test_router_explains_itself():
    d = HeuristicRouterPolicy().decide(_ctx(QUESTIONS[1]))
    assert "metric" in d.reason
    assert "difficulty" in d.features


# ── registry ─────────────────────────────────────────────────────────
def test_every_baseline_is_registered():
    assert set(registry.available_policies()) == {
        "role_table",
        "always_strong",
        "always_cheap",
        "heuristic_router",
    }
    assert set(BASELINES) == set(registry.available_policies())


def test_get_policy_by_name_is_case_insensitive():
    assert registry.get_policy("Heuristic_Router").name == "heuristic_router"


def test_unknown_policy_name_falls_back_to_role_table():
    assert registry.get_policy("does-not-exist").name == "role_table"


def test_decide_defaults_to_role_table(monkeypatch):
    monkeypatch.setattr(registry, "_configured_name", lambda: "role_table")
    monkeypatch.setattr(registry, "_configured_limits", lambda: (6, 12_000))
    d = registry.decide("How many PRs merged last week?")
    assert d == RoleTablePolicy().decide(_ctx("How many PRs merged last week?")).clamped()


def test_decide_uses_configured_policy(monkeypatch):
    monkeypatch.setattr(registry, "_configured_name", lambda: "always_cheap")
    assert registry.decide("anything").policy == "always_cheap"


def test_a_crashing_policy_never_fails_the_turn():
    class Broken:
        name = "broken"

        def decide(self, ctx):
            raise RuntimeError("boom")

    d = registry.decide("anything", policy=Broken())
    assert d.policy == "role_table"
    assert "fallback" in d.reason


def test_a_policy_returning_garbage_falls_back():
    class Garbage:
        name = "garbage"

        def decide(self, ctx):
            return {"model_tier": "cheap"}

    assert registry.decide("anything", policy=Garbage()).policy == "role_table"


def test_decide_always_clamps():
    class Greedy:
        name = "greedy"

        def decide(self, ctx):
            return PolicyDecision(
                max_tool_turns=10_000, history_token_budget=10**9, policy="greedy"
            )

    d = registry.decide("anything", policy=Greedy())
    assert d.policy == "greedy"
    assert d.max_tool_turns <= 16
    assert d.history_token_budget <= 64_000


def test_featurize_failure_still_produces_a_decision(monkeypatch):
    def explode(*a, **k):
        raise ValueError("bad input")

    monkeypatch.setattr(registry, "featurize", explode)
    d = registry.decide("anything", policy=RoleTablePolicy())
    assert d.policy == "role_table"
    assert d.features["query_chars"] == 0.0
