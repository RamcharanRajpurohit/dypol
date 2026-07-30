"""Per-provider token pricing → ``cost_usd``.

FUTURE_PLAN §2.4 lists "no cost accounting per turn" as a gap: Langfuse is
wired, but nothing puts a ``cost_usd`` on a trace row, so there is no reward to
train a policy on. This module is that number.

Design notes
------------
**Prices are data, not code.** The table below is a snapshot with an explicit
observation date and source URL per provider, and every entry can be
overridden at runtime via ``MODEL_PRICING_JSON`` (a path to a JSON file) —
because provider pricing churns and a stale hard-coded constant silently
poisons every downstream cost figure. §4.1 of the plan documents one such
churn inside 2026 already.

**Unknown models cost ``None``, never 0.0.** A zero would flow into a mean and
read as "this was free"; ``None`` forces the caller to decide. ``estimate``
returns a ``TokenCost`` whose ``usd`` is None when the model isn't priced, and
``priced`` says which case you're in.

**Rates are per 1M tokens** to match how every provider publishes them, and
are converted at the point of use — keeping the table diffable against the
source pages.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

log = logging.getLogger("dypol.telemetry.cost")

# Sources, all observed 2026-07-30:
#   Anthropic — https://platform.claude.com/docs/en/about-claude/models/overview
#   Google    — https://ai.google.dev/gemini-api/docs/pricing
#   Groq      — https://groq.com/pricing/
#   OpenAI    — https://developers.openai.com/api/docs/pricing
#
# Keys are matched case-insensitively, longest-prefix-first, so a versioned id
# like "gemini-2.5-flash-preview-09" still resolves to "gemini-2.5-flash".
PRICING_OBSERVED_AT = "2026-07-30"

_PRICING_PER_1M: dict[str, tuple[float, float]] = {
    # ── Google Gemini ────────────────────────────────────────────────
    # NOTE: the 3.5 generation moved the whole ladder up a rung —
    # gemini-3.5-flash output is $9.00 vs 2.5-flash's $2.50 (3.6x). A
    # "just upgrade to 3.5-flash" would be a large silent cost increase;
    # gemini-3.5-flash-lite is the cost-neutral swap for 2.5-flash.
    "gemini-3.6-flash": (1.50, 7.50),
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.5-flash": (1.50, 9.00),
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
    # ── Groq ─────────────────────────────────────────────────────────
    "openai/gpt-oss-120b": (0.15, 0.60),
    "openai/gpt-oss-20b": (0.075, 0.30),
    # ── Anthropic ────────────────────────────────────────────────────
    "claude-fable-5": (10.00, 50.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    # ── OpenAI ───────────────────────────────────────────────────────
    "gpt-5.6-sol": (5.00, 30.00),
    "gpt-5.6-terra": (2.50, 15.00),
    "gpt-5.6-luna": (1.00, 6.00),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.4-nano": (0.20, 1.25),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5-nano": (0.05, 0.40),
}

# Embeddings price input only; output is meaningless for them.
_EMBED_PRICING_PER_1M: dict[str, float] = {
    "gemini-embedding-001": 0.15,
    "gemini-embedding-2": 0.15,
}


@dataclass(frozen=True, slots=True)
class TokenCost:
    """The cost of one model call, plus whether we actually knew the price."""

    usd: float | None
    input_tokens: int
    output_tokens: int
    model: str
    priced: bool

    @property
    def usd_or_zero(self) -> float:
        """For summing. Read ``priced`` first if the distinction matters —
        an unpriced call contributes 0 here and will understate a total."""
        return self.usd or 0.0


@lru_cache(maxsize=1)
def _pricing() -> dict[str, tuple[float, float]]:
    """The active table: built-in defaults, overlaid with MODEL_PRICING_JSON.

    The override file is ``{"model-id": [input_per_1m, output_per_1m], ...}``.
    It exists so a price change can be deployed as config rather than a code
    change — and so a benchmark run can pin the prices it was costed at.
    """
    table = dict(_PRICING_PER_1M)
    path = os.environ.get("MODEL_PRICING_JSON")
    if not path:
        return table
    try:
        with open(path) as fh:
            raw: dict[str, Any] = json.load(fh)
        for model, pair in raw.items():
            table[model.lower()] = (float(pair[0]), float(pair[1]))
        log.info("cost: applied %d price override(s) from %s", len(raw), path)
    except Exception as exc:
        # A malformed override must not take the app down or, worse, silently
        # zero out pricing — keep the defaults and say so loudly.
        log.warning("cost: ignoring MODEL_PRICING_JSON %s: %s", path, exc)
    return table


def _lookup(model: str, table: dict[str, tuple[float, float]]) -> tuple[float, float] | None:
    """Longest-prefix match, so versioned/suffixed ids resolve to their family."""
    needle = (model or "").strip().lower()
    if not needle:
        return None
    if needle in table:
        return table[needle]
    best: str | None = None
    for key in table:
        if needle.startswith(key) and (best is None or len(key) > len(best)):
            best = key
    return table[best] if best else None


def estimate(model: str, input_tokens: int, output_tokens: int) -> TokenCost:
    """Cost of one call. ``usd`` is None (and ``priced`` False) if unknown."""
    rates = _lookup(model, _pricing())
    if rates is None:
        return TokenCost(None, input_tokens, output_tokens, model, priced=False)
    in_rate, out_rate = rates
    usd = (input_tokens / 1_000_000) * in_rate + (output_tokens / 1_000_000) * out_rate
    return TokenCost(round(usd, 8), input_tokens, output_tokens, model, priced=True)


def estimate_embedding(model: str, input_tokens: int) -> TokenCost:
    """Cost of an embedding call (input-priced only)."""
    needle = (model or "").strip().lower()
    rate = _EMBED_PRICING_PER_1M.get(needle)
    if rate is None:
        for key, value in _EMBED_PRICING_PER_1M.items():
            if needle.startswith(key):
                rate = value
                break
    if rate is None:
        return TokenCost(None, input_tokens, 0, model, priced=False)
    return TokenCost(
        round((input_tokens / 1_000_000) * rate, 8), input_tokens, 0, model, priced=True
    )


def is_priced(model: str) -> bool:
    """True if we have a rate for this model — use to alert on gaps."""
    return _lookup(model, _pricing()) is not None


def known_models() -> list[str]:
    """Every priced model id, for diagnostics and coverage checks."""
    return sorted(_pricing())
