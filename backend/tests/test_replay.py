"""Offline replay — the cost half of the Phase-1 policy re-scoring harness."""
from __future__ import annotations

import pytest

from app.services.agent_runs import _percentile
from app.telemetry import cost
from app.telemetry.replay import replay


def _run(*calls):
    return {"model_calls": [dict(c) for c in calls]}


def _call(model, tin, tout):
    return {"model": model, "input_tokens": tin, "output_tokens": tout}


def test_identity_map_has_zero_saving():
    runs = [_run(_call("gemini-2.5-flash", 1_000_000, 100_000))]
    r = replay(runs, model_map={})
    assert r.baseline_usd == pytest.approx(r.counterfactual_usd)
    assert r.saving_usd == 0
    assert r.saving_pct == 0


def test_swap_to_lite_prices_with_target_rates():
    # 2.5-flash: 0.30/2.50 ; 2.5-flash-lite: 0.10/0.40 (per 1M)
    runs = [_run(_call("gemini-2.5-flash", 1_000_000, 1_000_000))]
    r = replay(runs, model_map={"gemini-2.5-flash": "gemini-2.5-flash-lite"})
    assert r.baseline_usd == pytest.approx(2.80)
    assert r.counterfactual_usd == pytest.approx(0.50)
    assert r.saving_pct == pytest.approx(82.14, abs=0.01)


def test_unpriced_calls_are_counted_and_excluded():
    runs = [_run(_call("mystery-model", 1000, 1000), _call("gemini-2.5-flash", 1000, 1000))]
    r = replay(runs, model_map={})
    assert r.calls == 2
    assert r.unpriced_calls == 1
    # The unpriced call contributes to neither side of the comparison.
    assert r.baseline_usd == pytest.approx(cost.estimate("gemini-2.5-flash", 1000, 1000).usd)


def test_price_overrides_never_touch_live_pricing():
    """A what-if must not re-price real traffic (the live table is cached)."""
    before = cost.estimate("gemini-2.5-flash", 1_000_000, 0).usd
    runs = [_run(_call("gemini-2.5-flash", 1_000_000, 0))]
    r = replay(runs, model_map={}, price_overrides={"gemini-2.5-flash": (99.0, 99.0)})
    assert r.counterfactual_usd == pytest.approx(99.0)
    assert r.baseline_usd == pytest.approx(before)
    assert cost.estimate("gemini-2.5-flash", 1_000_000, 0).usd == pytest.approx(before)


def test_percentile_bounds_and_unsorted_input():
    assert _percentile([], 0.95) == 0.0
    assert _percentile([1.0], 0.95) == 1.0
    assert _percentile([4, 1, 3, 2], 0.5) == 3
    assert _percentile([900, 10, 20, 30], 0.95) == 900
