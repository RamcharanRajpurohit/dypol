"""Applying a :class:`PolicyDecision` to the concrete agent machinery.

The graph should not need to know what a tier or a scope *means*; it asks
these helpers for the chain to walk, the tools to bind, the history budget to
trim to and the retrieval depth to default to. Keeping every interpretation
here means a new policy can never be half-applied (say, a tier honoured by the
orchestrator but ignored by the streaming path).

Invariant shared by all helpers: **a decision can only narrow or reorder, never
remove the last safe option.** A cheap tier still has the strong model later in
its chain; a CORE scope still keeps every core tool that is available; an
empty filter result falls back to the unfiltered list.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.policy.decision import HistoryDepth, ModelTier, PolicyDecision, RetrievalDepth, ToolScope

# ── model axis ───────────────────────────────────────────────────────


def order_chain(
    chain: Sequence[tuple[str, bool]], tier: ModelTier
) -> list[tuple[str, bool]]:
    """Reorder ``model_chain()`` so ``tier`` is tried first on each provider.

    ``chain`` is ``[(provider, use_fallback), ...]`` with the strong model
    (``use_fallback=False``) first per provider. For ``CHEAP`` each provider's
    pair is swapped, so a quota/hard error on the cheap model still escalates
    to that provider's strong model before moving to the next provider —
    provider order is never changed, only the tier order within a provider.
    """
    if tier is ModelTier.STRONG:
        return list(chain)
    out: list[tuple[str, bool]] = []
    seen: list[str] = []
    for provider, _ in chain:
        if provider not in seen:
            seen.append(provider)
    for provider in seen:
        steps = [step for step in chain if step[0] == provider]
        cheap = [s for s in steps if s[1]]
        strong = [s for s in steps if not s[1]]
        out.extend(cheap + strong)
    return out


# ── tool-scope axis ──────────────────────────────────────────────────

# Tools that answer the bread-and-butter GitHub/workspace questions. Anything
# not listed here (web search, code execution, semantic search, sub-agents) is
# an "extended" tool that a CORE turn does without.
CORE_TOOLS: frozenset[str] = frozenset(
    {
        "github_get",
        "github_search",
        "github_graphql",
        "workspace_info",
        "current_datetime",
        "summarize",
        "remember",
    }
)
DELEGATE_PREFIX = "delegate_"


def _name(tool: Any) -> str:
    return str(getattr(tool, "name", "") or "")


def scope_tools(tools: Sequence[Any], scope: ToolScope) -> list[Any]:
    """Filter a built tool list to ``scope``.

    * ``ALL``       — unchanged (today's behaviour).
    * ``DELEGATES`` — core tools + ``delegate_*`` sub-agent tools.
    * ``CORE``      — core tools only.

    Falls back to the unfiltered list if the filter would leave nothing to
    call: a workspace whose only available tool is, say, ``semantic_search``
    must not be left toolless by a CORE decision.
    """
    if scope is ToolScope.ALL:
        return list(tools)
    if scope is ToolScope.DELEGATES:
        kept = [t for t in tools if _name(t) in CORE_TOOLS or _name(t).startswith(DELEGATE_PREFIX)]
    else:
        kept = [t for t in tools if _name(t) in CORE_TOOLS]
    return kept or list(tools)


def wants_delegates(scope: ToolScope) -> bool:
    """Whether the sub-agent delegate tools should be built at all — skipping
    them for CORE avoids constructing sub-agent graphs that will never run."""
    return scope is not ToolScope.CORE


# ── memory axis ──────────────────────────────────────────────────────

SHORT_HISTORY_TOKENS = 3_000
RETRIEVAL_K: dict[RetrievalDepth, int | None] = {
    RetrievalDepth.NONE: 0,
    RetrievalDepth.SMALL: 4,
    RetrievalDepth.LARGE: 16,
    RetrievalDepth.DEFAULT: None,
}


def history_budget(depth: HistoryDepth, configured: int) -> int:
    """Token budget for ``trim_history`` at ``depth``.

    ``NONE`` is 0: ``trim_history`` always keeps the newest message, so the
    model still sees the current question — just nothing before it.
    """
    if depth is HistoryDepth.NONE:
        return 0
    if depth is HistoryDepth.SHORT:
        return min(SHORT_HISTORY_TOKENS, configured)
    return configured


def retrieval_k(depth: RetrievalDepth) -> int | None:
    """Default ``k`` for ``semantic_search`` (None → settings default)."""
    return RETRIEVAL_K[depth]


def drop_disabled_tools(tools: Sequence[Any], decision: PolicyDecision) -> list[Any]:
    """Remove tools the decision turned off entirely.

    Retrieval depth ``NONE`` means "no semantic search this turn". Passing
    ``k=0`` would not do it — the handler treats a falsy ``k`` as "use the
    default" — so the tool is unbound instead, which also saves its schema
    tokens. Same fallback rule as :func:`scope_tools`: never leave nothing.
    """
    if decision.retrieval is not RetrievalDepth.NONE:
        return list(tools)
    kept = [t for t in tools if _name(t) != "semantic_search"]
    return kept or list(tools)


def apply_to_install(install: dict[str, Any], decision: PolicyDecision) -> dict[str, Any]:
    """Return a copy of ``install`` carrying the per-turn tool defaults.

    Tool handler factories receive the install dict, so this is how the
    retrieval depth reaches ``semantic_search`` without changing every
    factory's signature. Keys are underscore-prefixed: per-turn, not stored.
    """
    out = dict(install)
    out["_policy_retrieval_k"] = decision.retrieval_k
    return out
