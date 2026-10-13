"""PolicyDecision — clamping, serialisation, and the factored action encoding."""

from __future__ import annotations

import json

import pytest

from app.policy.decision import (
    ACTION_FEATURE_NAMES,
    MAX_HISTORY_TOKENS,
    MAX_RETRIEVAL_K,
    MAX_TOOL_TURNS,
    MIN_TOOL_TURNS,
    EffortLevel,
    HistoryDepth,
    ModelTier,
    PolicyDecision,
    RetrievalDepth,
    ToolScope,
)


def test_defaults_describe_todays_behaviour():
    d = PolicyDecision()
    assert d.model_tier is ModelTier.STRONG
    assert d.effort is EffortLevel.DEFAULT
    assert d.max_tool_turns == 6
    assert d.history is HistoryDepth.FULL
    assert d.history_token_budget == 12_000
    assert d.retrieval is RetrievalDepth.DEFAULT
    assert d.retrieval_k is None
    assert d.tool_scope is ToolScope.ALL
    assert d.policy == "role_table"


def test_decision_is_immutable():
    d = PolicyDecision()
    with pytest.raises(AttributeError):
        d.max_tool_turns = 99  # type: ignore[misc]


@pytest.mark.parametrize(
    ("turns", "expected"),
    [(0, MIN_TOOL_TURNS), (-5, MIN_TOOL_TURNS), (3, 3), (10_000, MAX_TOOL_TURNS)],
)
def test_clamp_bounds_tool_turns(turns, expected):
    assert PolicyDecision(max_tool_turns=turns).clamped().max_tool_turns == expected


def test_clamp_bounds_history_and_retrieval():
    d = PolicyDecision(history_token_budget=10**9, retrieval_k=10**6).clamped()
    assert d.history_token_budget == MAX_HISTORY_TOKENS
    assert d.retrieval_k == MAX_RETRIEVAL_K
    assert PolicyDecision(history_token_budget=-1).clamped().history_token_budget == 0
    assert PolicyDecision(retrieval_k=-3).clamped().retrieval_k == 0


def test_clamp_keeps_none_retrieval_k():
    assert PolicyDecision(retrieval_k=None).clamped().retrieval_k is None


def test_history_none_forces_zero_budget_even_if_policy_forgot():
    d = PolicyDecision(history=HistoryDepth.NONE, history_token_budget=8_000).clamped()
    assert d.history_token_budget == 0


def test_with_reason_returns_a_new_decision():
    d = PolicyDecision()
    d2 = d.with_reason("because")
    assert d2.reason == "because"
    assert d.reason == ""


def test_to_dict_is_json_safe_and_round_trips():
    d = PolicyDecision(
        model_tier=ModelTier.CHEAP,
        effort=EffortLevel.HIGH,
        max_tool_turns=12,
        history=HistoryDepth.SHORT,
        history_token_budget=3_000,
        retrieval=RetrievalDepth.LARGE,
        retrieval_k=16,
        tool_scope=ToolScope.CORE,
        policy="heuristic_router",
        reason="code question",
        features={"query_words": 12.0},
    )
    raw = d.to_dict()
    json.dumps(raw)  # must not raise: enums are serialised as strings
    assert raw["model_tier"] == "cheap"
    assert raw["tool_scope"] == "core"
    assert PolicyDecision.from_dict(raw) == d


def test_from_dict_tolerates_old_or_bad_rows():
    """A stored trace from an older schema must still load for replay."""
    d = PolicyDecision.from_dict(
        {"model_tier": "turbo", "effort": "low", "unknown_field": 1, "max_tool_turns": 4}
    )
    assert d.model_tier is ModelTier.STRONG  # bad enum → field default
    assert d.effort is EffortLevel.LOW
    assert d.max_tool_turns == 4


def test_from_dict_of_empty_is_default():
    assert PolicyDecision.from_dict({}) == PolicyDecision()


def test_action_vector_is_one_hot_per_axis():
    vec = PolicyDecision().action_vector()
    assert len(vec) == len(ACTION_FEATURE_NAMES)
    # Exactly one active column per axis (5 axes).
    assert sum(vec) == 5
    assert set(vec) <= {0.0, 1.0}


def test_action_vector_marks_the_chosen_arms():
    d = PolicyDecision(model_tier=ModelTier.CHEAP, tool_scope=ToolScope.CORE)
    active = {name for name, v in zip(ACTION_FEATURE_NAMES, d.action_vector(), strict=True) if v}
    assert "ModelTier.cheap" in active
    assert "ToolScope.core" in active
    assert "ModelTier.strong" not in active


def test_effort_rank_is_ordinal():
    ranks = [
        e.rank for e in (EffortLevel.NONE, EffortLevel.LOW, EffortLevel.MEDIUM, EffortLevel.HIGH)
    ]
    assert ranks == sorted(ranks)
    assert EffortLevel.DEFAULT.rank == EffortLevel.MEDIUM.rank
