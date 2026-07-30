"""Cost accounting — the reward signal Phase 3's bandit trains against.

If these numbers are wrong every downstream cost claim in the report is wrong,
so the invariants worth guarding are: a known model prices exactly, an unknown
model is *unpriced* rather than free, and a bad override file can't silently
zero the table.
"""
from __future__ import annotations

import json

import pytest

from app.telemetry import cost


def test_known_model_prices_exactly():
    # gemini-2.5-flash: $0.30 in / $2.50 out per 1M (observed 2026-07-30)
    c = cost.estimate("gemini-2.5-flash", input_tokens=1_000_000, output_tokens=1_000_000)
    assert c.priced is True
    assert c.usd == pytest.approx(0.30 + 2.50)


def test_partial_million_scales_linearly():
    c = cost.estimate("openai/gpt-oss-20b", input_tokens=500_000, output_tokens=100_000)
    # $0.075/1M in, $0.30/1M out
    assert c.usd == pytest.approx(0.075 * 0.5 + 0.30 * 0.1)


def test_unknown_model_is_unpriced_not_free():
    """A zero here would flow into a mean and read as 'this call was free'."""
    c = cost.estimate("some-model-we-have-never-seen", 1000, 1000)
    assert c.priced is False
    assert c.usd is None
    assert c.usd_or_zero == 0.0  # explicit opt-in for summing


def test_versioned_id_resolves_to_its_family():
    """Providers append suffixes; a preview id must not fall off the table."""
    exact = cost.estimate("gemini-2.5-flash", 1000, 1000)
    suffixed = cost.estimate("gemini-2.5-flash-preview-09-2025", 1000, 1000)
    assert suffixed.priced is True
    assert suffixed.usd == exact.usd


def test_longest_prefix_wins_over_shorter_family():
    """'gemini-2.5-flash-lite' must not be priced as 'gemini-2.5-flash'."""
    lite = cost.estimate("gemini-2.5-flash-lite", 1_000_000, 0)
    flash = cost.estimate("gemini-2.5-flash", 1_000_000, 0)
    assert lite.usd == pytest.approx(0.10)
    assert flash.usd == pytest.approx(0.30)
    assert lite.usd != flash.usd


def test_longest_prefix_wins_regardless_of_table_order():
    """Direct test of the matcher with an adversarial table.

    The test above passes even under a first-match-wins implementation,
    because the shipped table happens to list the longer key first — so it
    proves nothing about the matching rule. Here the SHORT key is inserted
    first, so first-match-wins would return the wrong rate.
    """
    table = {"model-x": (1.0, 1.0), "model-x-lite": (2.0, 2.0)}
    # The needle must NOT be an exact key, or the exact-match fast path
    # answers before the prefix loop ever runs and the test proves nothing.
    assert cost._lookup("model-x-lite-preview-09", table) == (2.0, 2.0)
    assert cost._lookup("model-x-preview-09", table) == (1.0, 1.0)


def test_model_id_matching_is_case_insensitive():
    assert cost.estimate("GEMINI-2.5-FLASH", 1000, 0).priced is True


def test_empty_model_is_unpriced():
    assert cost.estimate("", 1000, 1000).priced is False


def test_embedding_is_input_priced_only():
    c = cost.estimate_embedding("gemini-embedding-001", input_tokens=2_000_000)
    assert c.priced is True
    assert c.usd == pytest.approx(0.30)  # $0.15/1M × 2M
    assert c.output_tokens == 0


def test_the_models_this_deployment_actually_uses_are_priced():
    """Guards the gap that matters: shipping a model with no rate means every
    turn on it is silently uncosted."""
    for model in ("gemini-2.5-flash", "gemini-2.5-flash-lite", "openai/gpt-oss-120b"):
        assert cost.is_priced(model), f"{model} has no price — cost tracking would be blind"


def test_override_file_replaces_a_rate(tmp_path, monkeypatch):
    override = tmp_path / "pricing.json"
    override.write_text(json.dumps({"gemini-2.5-flash": [99.0, 100.0]}))
    monkeypatch.setenv("MODEL_PRICING_JSON", str(override))
    cost._pricing.cache_clear()
    try:
        assert cost.estimate("gemini-2.5-flash", 1_000_000, 0).usd == pytest.approx(99.0)
    finally:
        cost._pricing.cache_clear()


def test_malformed_override_falls_back_instead_of_zeroing_the_table(tmp_path, monkeypatch):
    """A broken price file must not make everything look free."""
    bad = tmp_path / "bad.json"
    bad.write_text("{ this is not json")
    monkeypatch.setenv("MODEL_PRICING_JSON", str(bad))
    cost._pricing.cache_clear()
    try:
        c = cost.estimate("gemini-2.5-flash", 1_000_000, 0)
        assert c.priced is True
        assert c.usd == pytest.approx(0.30)  # built-in default survived
    finally:
        cost._pricing.cache_clear()


def test_missing_override_path_is_not_fatal(monkeypatch):
    monkeypatch.setenv("MODEL_PRICING_JSON", "/nonexistent/pricing.json")
    cost._pricing.cache_clear()
    try:
        assert cost.estimate("gemini-2.5-flash", 1_000_000, 0).priced is True
    finally:
        cost._pricing.cache_clear()


# ── Turn-level accounting (the reward signal itself) ─────────────────
def test_trace_collector_totals_a_turn():
    from app.agents.tracing import TraceCollector

    c = TraceCollector()
    c.record_model_call("gemini-2.5-flash", 1_000_000, 1_000_000, duration_ms=1200)
    c.record_model_call("gemini-2.5-flash-lite", 1_000_000, 0, duration_ms=300)
    s = c.usage_summary()
    assert s["model_calls"] == 2
    assert s["input_tokens"] == 2_000_000
    assert s["output_tokens"] == 1_000_000
    assert s["cost_usd"] == pytest.approx(0.30 + 2.50 + 0.10)
    assert s["latency_ms"] == 1500
    assert s["fully_priced"] is True


def test_an_unpriced_call_flags_the_turn_as_not_fully_priced():
    """Otherwise a partial total silently reads as the whole cost."""
    from app.agents.tracing import TraceCollector

    c = TraceCollector()
    c.record_model_call("gemini-2.5-flash", 1_000_000, 0)
    c.record_model_call("some-unknown-model", 1_000_000, 0)
    s = c.usage_summary()
    assert s["fully_priced"] is False
    assert s["cost_usd"] == pytest.approx(0.30)  # only what we could price


def test_usage_extraction_from_langchain_metadata():
    from app.agents.usage import extract_usage, model_name_of

    class Msg:
        usage_metadata = {"input_tokens": 11, "output_tokens": 960}
        response_metadata = {"model_name": "gemini-2.5-flash"}

    assert extract_usage(Msg()) == (11, 960)
    assert model_name_of(Msg(), fallback="x") == "gemini-2.5-flash"


def test_usage_extraction_falls_back_to_provider_shapes():
    from app.agents.usage import extract_usage

    class OpenAIish:
        usage_metadata = None
        response_metadata = {"token_usage": {"prompt_tokens": 5, "completion_tokens": 7}}

    class Googleish:
        usage_metadata = None
        response_metadata = {
            "usage_metadata": {"prompt_token_count": 3, "candidates_token_count": 4}
        }

    assert extract_usage(OpenAIish()) == (5, 7)
    assert extract_usage(Googleish()) == (3, 4)


def test_usage_extraction_returns_zero_when_truly_unknown():
    from app.agents.usage import extract_usage

    class Bare:
        pass

    assert extract_usage(Bare()) == (0, 0)
