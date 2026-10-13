"""Effort ladder → per-provider request parameters (FUTURE_PLAN §4.1).

Reasoning effort is categorical and provider-specific, and sending the wrong
parameter is not a no-op — Anthropic returns HTTP 400 for ``budget_tokens``
on models where it was removed. So this module is the *only* place that knows
how a rung of the ladder becomes request kwargs, and it gates every mapping on
a **capability probe** keyed by model family:

* a model we have no rule for gets **no effort parameters at all** (it runs
  exactly as it does today), and
* ``EffortLevel.DEFAULT`` always maps to nothing, on every model.

Each mapping is an :class:`EffortSpec` rather than a bare kwargs dict because
some providers couple effort to *other* parameters: Anthropic extended
thinking requires ``temperature=1`` and a ``max_tokens`` larger than the
thinking budget, so those have to be overridden together or the request fails.

Second dial: the tool-turn cap. It is provider-uniform, already enforced by the
graph, and therefore the safe effort control on models with no native knob.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.policy.decision import EffortLevel

# Tool-turn cap per rung. MEDIUM/DEFAULT match today's AGENT_MAX_TOOL_TURNS
# default of 6, so the default policy reproduces current behaviour exactly.
TOOL_TURNS_BY_EFFORT: dict[EffortLevel, int] = {
    EffortLevel.NONE: 2,
    EffortLevel.LOW: 4,
    EffortLevel.MEDIUM: 6,
    EffortLevel.DEFAULT: 6,
    EffortLevel.HIGH: 12,
}


@dataclass(frozen=True, slots=True)
class EffortSpec:
    """What to change on the model constructor for one effort rung."""

    kwargs: dict[str, Any] = field(default_factory=dict)
    temperature: float | None = None  # override settings.agent_temperature
    min_max_tokens: int | None = None  # raise max output tokens to at least this
    supported: bool = True  # False → the probe rejected this model

    @property
    def is_noop(self) -> bool:
        return not self.kwargs and self.temperature is None and self.min_max_tokens is None


NOOP = EffortSpec()
UNSUPPORTED = EffortSpec(supported=False)


# ── capability probe ─────────────────────────────────────────────────
# Ordered (pattern, family) pairs; first match wins. Patterns are matched
# against the lower-cased model id.
_FAMILIES: list[tuple[re.Pattern[str], str]] = [
    # OpenAI reasoning models accept reasoning_effort; gpt-4o/4.1 do not.
    (re.compile(r"^(o[1-9](-mini|-pro)?|gpt-5)"), "openai_reasoning"),
    # Groq-hosted gpt-oss exposes reasoning_effort (low/medium/high).
    (re.compile(r"^openai/gpt-oss"), "groq_gpt_oss"),
    # Gemini 3+ uses thinking_level; 2.5 uses an integer thinking_budget.
    (re.compile(r"^gemini-(3|4)"), "gemini_level"),
    (re.compile(r"^gemini-2\.5-pro"), "gemini_budget_pro"),
    (re.compile(r"^gemini-2\.5-flash"), "gemini_budget_flash"),
    # Anthropic: 4.6+ / 5.x take adaptive thinking; budget_tokens is
    # deprecated there and a hard error on Opus 4.7+ / Sonnet 5.
    (re.compile(r"^claude-(opus|sonnet|haiku|fable)-(4-[6-9]|5)"), "anthropic_adaptive"),
    # Anthropic 4.5-and-earlier thinking models still take budget_tokens.
    (re.compile(r"^claude-(opus|sonnet|haiku)-4(-[0-5])?\b"), "anthropic_budget"),
    (re.compile(r"^claude-3-7-sonnet"), "anthropic_budget"),
]


def model_family(model: str) -> str | None:
    """The effort family for ``model``, or None if we have no safe mapping."""
    needle = (model or "").strip().lower()
    for pattern, family in _FAMILIES:
        if pattern.search(needle):
            return family
    return None


def supports_effort(model: str) -> bool:
    return model_family(model) is not None


# ── per-family mappings ──────────────────────────────────────────────
_OPENAI_EFFORT = {
    EffortLevel.NONE: "minimal",
    EffortLevel.LOW: "low",
    EffortLevel.MEDIUM: "medium",
    EffortLevel.HIGH: "high",
}
# gpt-oss has no "minimal"; low is the floor.
_GPT_OSS_EFFORT = {
    EffortLevel.NONE: "low",
    EffortLevel.LOW: "low",
    EffortLevel.MEDIUM: "medium",
    EffortLevel.HIGH: "high",
}
_GEMINI_LEVEL = {
    EffortLevel.NONE: "LOW",  # Gemini 3 cannot fully disable thinking
    EffortLevel.LOW: "LOW",
    EffortLevel.MEDIUM: "MEDIUM",
    EffortLevel.HIGH: "HIGH",
}
# thinking_budget in tokens. Flash can disable thinking (0); Pro's floor is 128.
_GEMINI_FLASH_BUDGET = {
    EffortLevel.NONE: 0,
    EffortLevel.LOW: 1_024,
    EffortLevel.MEDIUM: 8_192,
    EffortLevel.HIGH: 24_576,
}
_GEMINI_PRO_BUDGET = {
    EffortLevel.NONE: 128,
    EffortLevel.LOW: 1_024,
    EffortLevel.MEDIUM: 8_192,
    EffortLevel.HIGH: 32_768,
}
_ANTHROPIC_BUDGET = {
    EffortLevel.LOW: 1_024,
    EffortLevel.MEDIUM: 4_096,
    EffortLevel.HIGH: 16_000,
}
# Output headroom kept on top of a thinking budget so the visible answer
# isn't starved by the reasoning it was granted.
_ANSWER_HEADROOM = 1_200


def effort_spec(model: str, effort: EffortLevel) -> EffortSpec:
    """Map one ladder rung onto ``model``'s request parameters.

    Returns :data:`NOOP` for ``DEFAULT`` (and for ``NONE`` where "no thinking"
    is simply the absence of the parameter), and :data:`UNSUPPORTED` when the
    probe has no rule for the model — callers treat both as "send nothing".
    """
    if effort is EffortLevel.DEFAULT:
        return NOOP
    family = model_family(model)
    if family is None:
        return UNSUPPORTED

    if family == "openai_reasoning":
        return EffortSpec(kwargs={"reasoning_effort": _OPENAI_EFFORT[effort]})
    if family == "groq_gpt_oss":
        return EffortSpec(kwargs={"reasoning_effort": _GPT_OSS_EFFORT[effort]})
    if family == "gemini_level":
        return EffortSpec(kwargs={"thinking_level": _GEMINI_LEVEL[effort]})
    if family == "gemini_budget_flash":
        return EffortSpec(kwargs={"thinking_budget": _GEMINI_FLASH_BUDGET[effort]})
    if family == "gemini_budget_pro":
        return EffortSpec(kwargs={"thinking_budget": _GEMINI_PRO_BUDGET[effort]})
    if family == "anthropic_adaptive":
        if effort is EffortLevel.NONE:
            return NOOP  # thinking off == don't send the parameter
        # Adaptive thinking: the model sizes its own reasoning. Extended
        # thinking is incompatible with temperature != 1.
        return EffortSpec(kwargs={"thinking": {"type": "adaptive"}}, temperature=1.0)
    if family == "anthropic_budget":
        if effort is EffortLevel.NONE:
            return NOOP
        budget = _ANTHROPIC_BUDGET[effort]
        return EffortSpec(
            kwargs={"thinking": {"type": "enabled", "budget_tokens": budget}},
            temperature=1.0,
            # max_tokens must exceed budget_tokens or the API rejects the call.
            min_max_tokens=budget + _ANSWER_HEADROOM,
        )
    return UNSUPPORTED  # pragma: no cover - every family is handled above


def apply_effort(
    kwargs: dict[str, Any], model: str, effort: EffortLevel, *, max_tokens_key: str
) -> dict[str, Any]:
    """Return a copy of model-constructor ``kwargs`` with ``effort`` applied.

    ``max_tokens_key`` is the provider's spelling of the output cap
    (``max_tokens`` vs Gemini's ``max_output_tokens``).
    """
    spec = effort_spec(model, effort)
    if not spec.supported or spec.is_noop:
        return dict(kwargs)
    out = {**kwargs, **spec.kwargs}
    if spec.temperature is not None:
        out["temperature"] = spec.temperature
    if spec.min_max_tokens is not None:
        current = int(out.get(max_tokens_key) or 0)
        out[max_tokens_key] = max(current, spec.min_max_tokens)
    return out


def tool_turns_for(effort: EffortLevel, default: int) -> int:
    """Tool-turn cap for a rung; ``DEFAULT`` keeps the configured value."""
    if effort is EffortLevel.DEFAULT:
        return default
    return TOOL_TURNS_BY_EFFORT[effort]
