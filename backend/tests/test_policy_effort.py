"""Effort ladder → provider parameters, gated by the capability probe.

The failure these guard against is not "wrong effort" — it is a request the
provider *rejects*: budget_tokens on a model that removed it, a thinking
budget larger than max_tokens, thinking with temperature != 1.
"""

from __future__ import annotations

import pytest

from app.policy.decision import EffortLevel
from app.policy.effort import (
    NOOP,
    TOOL_TURNS_BY_EFFORT,
    apply_effort,
    effort_spec,
    model_family,
    supports_effort,
    tool_turns_for,
)

ALL_RUNGS = [EffortLevel.NONE, EffortLevel.LOW, EffortLevel.MEDIUM, EffortLevel.HIGH]


@pytest.mark.parametrize(
    ("model", "family"),
    [
        ("gpt-5-mini", "openai_reasoning"),
        ("gpt-5.4-nano", "openai_reasoning"),
        ("o3", "openai_reasoning"),
        ("o4-mini", "openai_reasoning"),
        ("gpt-4o", None),
        ("gpt-4o-mini", None),
        ("openai/gpt-oss-120b", "groq_gpt_oss"),
        ("gemini-3.5-flash", "gemini_level"),
        ("gemini-2.5-pro", "gemini_budget_pro"),
        ("gemini-2.5-flash", "gemini_budget_flash"),
        ("gemini-2.5-flash-lite", "gemini_budget_flash"),
        ("claude-sonnet-4-6", "anthropic_adaptive"),
        ("claude-opus-4-8", "anthropic_adaptive"),
        ("claude-sonnet-5", "anthropic_adaptive"),
        ("claude-haiku-4-5", "anthropic_budget"),
        ("claude-3-7-sonnet-latest", "anthropic_budget"),
        ("llama-3.1-8b-instant", None),
        ("", None),
    ],
)
def test_model_family_probe(model, family):
    assert model_family(model) == family
    assert supports_effort(model) is (family is not None)


def test_probe_is_case_insensitive():
    assert model_family("Gemini-2.5-Flash") == "gemini_budget_flash"


@pytest.mark.parametrize(
    "model", ["gpt-5-mini", "claude-sonnet-4-6", "gemini-2.5-flash", "gpt-4o", "?"]
)
def test_default_rung_is_always_a_noop(model):
    assert effort_spec(model, EffortLevel.DEFAULT) is NOOP


@pytest.mark.parametrize("effort", ALL_RUNGS)
def test_unknown_model_gets_nothing(effort):
    spec = effort_spec("llama-3.1-8b-instant", effort)
    assert spec.supported is False
    base = {"temperature": 0.2, "max_tokens": 1200}
    assert apply_effort(base, "llama-3.1-8b-instant", effort, max_tokens_key="max_tokens") == base


def test_openai_reasoning_effort_values():
    got = [effort_spec("gpt-5-mini", e).kwargs["reasoning_effort"] for e in ALL_RUNGS]
    assert got == ["minimal", "low", "medium", "high"]


def test_gpt_oss_has_no_minimal_rung():
    assert effort_spec("openai/gpt-oss-20b", EffortLevel.NONE).kwargs == {"reasoning_effort": "low"}


def test_gemini3_uses_thinking_level_not_budget():
    spec = effort_spec("gemini-3.5-flash", EffortLevel.HIGH)
    assert spec.kwargs == {"thinking_level": "HIGH"}
    assert "thinking_budget" not in spec.kwargs


def test_gemini_flash_can_disable_thinking_but_pro_cannot():
    assert effort_spec("gemini-2.5-flash", EffortLevel.NONE).kwargs == {"thinking_budget": 0}
    assert effort_spec("gemini-2.5-pro", EffortLevel.NONE).kwargs["thinking_budget"] >= 128


def test_gemini_budget_is_monotonic_in_effort():
    budgets = [effort_spec("gemini-2.5-flash", e).kwargs["thinking_budget"] for e in ALL_RUNGS]
    assert budgets == sorted(budgets)


def test_anthropic_adaptive_never_sends_budget_tokens():
    """budget_tokens is a hard 400 on Opus 4.7+ / Sonnet 5."""
    for effort in (EffortLevel.LOW, EffortLevel.MEDIUM, EffortLevel.HIGH):
        spec = effort_spec("claude-sonnet-5", effort)
        assert spec.kwargs == {"thinking": {"type": "adaptive"}}
        assert spec.temperature == 1.0


def test_anthropic_none_means_no_thinking_parameter():
    assert effort_spec("claude-sonnet-4-6", EffortLevel.NONE).is_noop
    assert effort_spec("claude-haiku-4-5", EffortLevel.NONE).is_noop


def test_anthropic_budget_raises_max_tokens_above_the_budget():
    out = apply_effort(
        {"temperature": 0.2, "max_tokens": 1200},
        "claude-haiku-4-5",
        EffortLevel.HIGH,
        max_tokens_key="max_tokens",
    )
    budget = out["thinking"]["budget_tokens"]
    assert out["max_tokens"] > budget
    assert out["temperature"] == 1.0


def test_apply_effort_never_lowers_an_existing_max_tokens():
    out = apply_effort(
        {"max_tokens": 100_000}, "claude-haiku-4-5", EffortLevel.LOW, max_tokens_key="max_tokens"
    )
    assert out["max_tokens"] == 100_000


def test_apply_effort_respects_gemini_spelling_of_max_tokens():
    out = apply_effort(
        {"max_output_tokens": 1200},
        "gemini-2.5-flash",
        EffortLevel.HIGH,
        max_tokens_key="max_output_tokens",
    )
    assert out["thinking_budget"] == 24_576
    assert "max_tokens" not in out


def test_apply_effort_does_not_mutate_input():
    base = {"temperature": 0.2, "max_tokens": 1200}
    apply_effort(base, "claude-haiku-4-5", EffortLevel.HIGH, max_tokens_key="max_tokens")
    assert base == {"temperature": 0.2, "max_tokens": 1200}


def test_tool_turns_default_keeps_configured_value():
    assert tool_turns_for(EffortLevel.DEFAULT, 9) == 9


def test_tool_turns_ladder_is_monotonic_and_medium_matches_todays_default():
    ladder = [TOOL_TURNS_BY_EFFORT[e] for e in ALL_RUNGS]
    assert ladder == sorted(ladder)
    assert TOOL_TURNS_BY_EFFORT[EffortLevel.MEDIUM] == 6
