"""Offline replay — re-score stored agent runs under a counterfactual policy.

FUTURE_PLAN §8 Phase 1: "Build ``telemetry/replay.py`` — re-score a stored
trace under a different policy without re-running the agent". A full replay of
*quality* needs the eval harness; what we can answer exactly from the ledger
today is the *cost* side of the reward:

    "If every call routed to model A had gone to model B (same tokens),
     what would the last N turns have cost?"

That is the model axis of the policy (§6) with tokens held fixed — a lower
bound on the saving, since a cheaper model usually also emits fewer tokens.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.telemetry import cost


@dataclass(slots=True)
class ReplayResult:
    turns: int = 0
    calls: int = 0
    baseline_usd: float = 0.0
    counterfactual_usd: float = 0.0
    unpriced_calls: int = 0
    per_model: dict[str, float] = field(default_factory=dict)

    @property
    def saving_usd(self) -> float:
        return round(self.baseline_usd - self.counterfactual_usd, 8)

    @property
    def saving_pct(self) -> float:
        if not self.baseline_usd:
            return 0.0
        return round(100 * self.saving_usd / self.baseline_usd, 2)

    def as_dict(self) -> dict[str, Any]:
        return {
            "turns": self.turns,
            "calls": self.calls,
            "baseline_usd": round(self.baseline_usd, 8),
            "counterfactual_usd": round(self.counterfactual_usd, 8),
            "saving_usd": self.saving_usd,
            "saving_pct": self.saving_pct,
            "unpriced_calls": self.unpriced_calls,
            "per_model": self.per_model,
        }


def _price_table(
    overrides: dict[str, tuple[float, float]] | None,
) -> dict[str, tuple[float, float]]:
    """A private copy of the live table with hypothetical prices applied.

    The live table is ``lru_cache``d and shared by every request, so a what-if
    must never write into it — that would silently re-price real traffic.
    """
    table = dict(cost._pricing())
    for model, (in_rate, out_rate) in (overrides or {}).items():
        table[model.lower()] = (float(in_rate), float(out_rate))
    return table


def _estimate(table: dict[str, tuple[float, float]], model: str, tin: int, tout: int):
    rates = cost._lookup(model, table)
    if rates is None:
        return None
    return (tin / 1_000_000) * rates[0] + (tout / 1_000_000) * rates[1]


def replay(
    runs: list[dict[str, Any]],
    model_map: dict[str, str],
    price_overrides: dict[str, tuple[float, float]] | None = None,
) -> ReplayResult:
    """Re-price ``runs`` with every model in ``model_map`` swapped for its target.

    ``model_map`` is ``{"gemini-2.5-flash": "gemini-2.5-flash-lite", ...}``;
    models not in the map keep their own price. Tokens are held fixed.
    """
    live = dict(cost._pricing())
    what_if = _price_table(price_overrides)
    out = ReplayResult()
    for run in runs:
        out.turns += 1
        for call in run.get("model_calls", []):
            out.calls += 1
            src = call.get("model", "")
            tin = int(call.get("input_tokens") or 0)
            tout = int(call.get("output_tokens") or 0)
            dst = model_map.get(src, src)
            # Baseline is what the turn actually cost at live prices; the
            # counterfactual uses the what-if table (overrides applied).
            base = _estimate(live, src, tin, tout)
            alt = _estimate(what_if, dst, tin, tout)
            if base is None or alt is None:
                # Skip rather than count as $0 — a free side of the comparison
                # would fabricate (or hide) a saving.
                out.unpriced_calls += 1
                continue
            out.baseline_usd += base
            out.counterfactual_usd += alt
            out.per_model[dst] = round(out.per_model.get(dst, 0.0) + alt, 8)
    return out
