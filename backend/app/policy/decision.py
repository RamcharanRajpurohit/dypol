"""``PolicyDecision`` — one turn's choice along all four resource axes.

The decision is a frozen value object: produced once at the start of a turn,
threaded read-only through the graph, and recorded on the trace so a stored
turn can later be re-scored under a different policy (``telemetry/replay``).

It also defines the **factored action encoding** (§6): rather than treating
the 4 × 5 × 3 × 3 × 3 joint space as hundreds of independent arms, a linear
bandit sees one one-hot block per axis. :meth:`PolicyDecision.action_vector`
is that encoding, and :data:`ACTION_FEATURE_NAMES` names its columns.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from enum import Enum, StrEnum
from typing import Any


class ModelTier(StrEnum):
    """Which model on each provider answers first.

    ``STRONG`` is the provider's primary model, ``CHEAP`` its fallback model.
    The tier only reorders the fallback chain — a quota error on the first
    choice still walks the rest of the chain, so no tier can make a turn fail
    that would otherwise have succeeded.
    """

    STRONG = "strong"
    CHEAP = "cheap"


class EffortLevel(StrEnum):
    """Ordinal reasoning-effort ladder (§4.1).

    Deliberately *not* a token count: current frontier APIs expose effort as a
    categorical knob, and Anthropic hard-errors on the old ``budget_tokens``
    parameter for newer models. ``DEFAULT`` means "send nothing, keep the
    provider's own default" — the only rung guaranteed to be accepted by
    every model, and what today's code does.
    """

    DEFAULT = "default"
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @property
    def rank(self) -> int:
        return _EFFORT_RANK[self]


_EFFORT_RANK = {
    EffortLevel.NONE: 0,
    EffortLevel.LOW: 1,
    EffortLevel.DEFAULT: 2,  # provider defaults sit around "medium"
    EffortLevel.MEDIUM: 2,
    EffortLevel.HIGH: 3,
}


class HistoryDepth(StrEnum):
    """How much prior conversation the model sees."""

    NONE = "none"    # current question only
    SHORT = "short"  # a few recent exchanges
    FULL = "full"    # the configured history budget (today's behaviour)


class RetrievalDepth(StrEnum):
    """How many chunks ``semantic_search`` returns when the model doesn't ask."""

    NONE = "none"
    SMALL = "small"
    LARGE = "large"
    DEFAULT = "default"  # settings.rag_retrieval_k (today's behaviour)


class ToolScope(StrEnum):
    """Which tools are bound to the orchestrator.

    Fewer bound tools means fewer schema tokens on *every* model call of the
    turn — FUTURE_PLAN flags this as likely the cheapest win in the system.
    """

    CORE = "core"            # GitHub + workspace tools only
    DELEGATES = "delegates"  # core + sub-agent delegate tools
    ALL = "all"              # everything available (today's behaviour)


# Hard bounds every decision is clamped into, whatever policy produced it. A
# learned policy is allowed to be wrong; it is not allowed to be unbounded.
MIN_TOOL_TURNS = 1
MAX_TOOL_TURNS = 16
MAX_HISTORY_TOKENS = 64_000
MAX_RETRIEVAL_K = 32


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """The full resource decision for one agent turn."""

    model_tier: ModelTier = ModelTier.STRONG
    effort: EffortLevel = EffortLevel.DEFAULT
    max_tool_turns: int = 6
    history: HistoryDepth = HistoryDepth.FULL
    history_token_budget: int = 12_000
    retrieval: RetrievalDepth = RetrievalDepth.DEFAULT
    retrieval_k: int | None = None  # None → settings.rag_retrieval_k
    tool_scope: ToolScope = ToolScope.ALL
    policy: str = "role_table"
    # Free-form explanation for traces / debugging ("short metric question").
    reason: str = ""
    # The feature snapshot the decision was made from, for offline replay.
    features: dict[str, float] = field(default_factory=dict)

    # ── construction helpers ────────────────────────────────────────
    def clamped(self) -> PolicyDecision:
        """Return a copy with every numeric field forced into its hard bounds."""
        turns = max(MIN_TOOL_TURNS, min(int(self.max_tool_turns), MAX_TOOL_TURNS))
        budget = max(0, min(int(self.history_token_budget), MAX_HISTORY_TOKENS))
        k = self.retrieval_k
        if k is not None:
            k = max(0, min(int(k), MAX_RETRIEVAL_K))
        if self.history is HistoryDepth.NONE:
            budget = 0
        return replace(self, max_tool_turns=turns, history_token_budget=budget, retrieval_k=k)

    def with_reason(self, reason: str) -> PolicyDecision:
        return replace(self, reason=reason)

    # ── serialisation ────────────────────────────────────────────────
    def to_dict(self) -> dict[str, Any]:
        """JSON-safe dict (enums as their string values) for traces / Mongo."""
        raw = asdict(self)
        for key, value in raw.items():
            if isinstance(value, Enum):
                raw[key] = value.value
        return raw

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PolicyDecision:
        """Inverse of :meth:`to_dict`; unknown keys are ignored, bad enum
        values fall back to the field default rather than raising — a stored
        trace from an older schema must still load."""
        defaults = cls()
        kwargs: dict[str, Any] = {}
        enum_fields = {
            "model_tier": ModelTier,
            "effort": EffortLevel,
            "history": HistoryDepth,
            "retrieval": RetrievalDepth,
            "tool_scope": ToolScope,
        }
        for name in cls.__dataclass_fields__:
            if name not in data:
                continue
            value = data[name]
            enum_cls = enum_fields.get(name)
            if enum_cls is not None:
                try:
                    value = enum_cls(value)
                except ValueError:
                    value = getattr(defaults, name)
            kwargs[name] = value
        return cls(**kwargs)

    # ── factored action encoding (§6) ────────────────────────────────
    def action_vector(self) -> list[float]:
        """One-hot block per axis, concatenated. See ``ACTION_FEATURE_NAMES``."""
        vec: list[float] = []
        for enum_cls, value in (
            (ModelTier, self.model_tier),
            (EffortLevel, self.effort),
            (HistoryDepth, self.history),
            (RetrievalDepth, self.retrieval),
            (ToolScope, self.tool_scope),
        ):
            vec.extend(1.0 if member is value else 0.0 for member in enum_cls)
        return vec


ACTION_FEATURE_NAMES: list[str] = [
    f"{enum_cls.__name__}.{member.value}"
    for enum_cls in (ModelTier, EffortLevel, HistoryDepth, RetrievalDepth, ToolScope)
    for member in enum_cls
]
