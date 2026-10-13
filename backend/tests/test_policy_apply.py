"""Applying a decision: chain order, tool scope, memory, retrieval.

The shared invariant: a decision may narrow or reorder, but it can never take
away the last safe option.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.policy.axes import (
    CORE_TOOLS,
    SHORT_HISTORY_TOKENS,
    apply_to_install,
    drop_disabled_tools,
    history_budget,
    order_chain,
    retrieval_k,
    scope_tools,
    wants_delegates,
)
from app.policy.decision import HistoryDepth, ModelTier, PolicyDecision, RetrievalDepth, ToolScope

CHAIN = [("gemini", False), ("gemini", True), ("groq", False), ("groq", True)]


def _tools(*names):
    return [SimpleNamespace(name=n) for n in names]


def _names(tools):
    return [t.name for t in tools]


# ── model axis ───────────────────────────────────────────────────────
def test_strong_tier_keeps_the_chain_unchanged():
    assert order_chain(CHAIN, ModelTier.STRONG) == CHAIN


def test_cheap_tier_swaps_within_each_provider_only():
    assert order_chain(CHAIN, ModelTier.CHEAP) == [
        ("gemini", True),
        ("gemini", False),
        ("groq", True),
        ("groq", False),
    ]


def test_cheap_tier_preserves_every_step():
    """Reordering must never drop a fallback — that would turn a quota error
    the old chain survived into a failed turn."""
    assert sorted(order_chain(CHAIN, ModelTier.CHEAP)) == sorted(CHAIN)


def test_order_chain_handles_empty_and_single_provider():
    assert order_chain([], ModelTier.CHEAP) == []
    assert order_chain([("groq", False), ("groq", True)], ModelTier.CHEAP) == [
        ("groq", True),
        ("groq", False),
    ]


def test_order_chain_returns_a_copy():
    out = order_chain(CHAIN, ModelTier.STRONG)
    out.append(("x", False))
    assert len(CHAIN) == 4


# ── tool-scope axis ──────────────────────────────────────────────────
ALL_TOOLS = _tools(
    "github_get",
    "github_search",
    "workspace_info",
    "web_search",
    "semantic_search",
    "python_exec",
    "delegate_code_analyst",
    "delegate_web_researcher",
)


def test_scope_all_is_unchanged():
    assert _names(scope_tools(ALL_TOOLS, ToolScope.ALL)) == _names(ALL_TOOLS)


def test_scope_core_keeps_only_core_tools():
    kept = _names(scope_tools(ALL_TOOLS, ToolScope.CORE))
    assert kept == ["github_get", "github_search", "workspace_info"]
    assert set(kept) <= CORE_TOOLS


def test_scope_delegates_adds_subagents_but_not_extended_tools():
    kept = _names(scope_tools(ALL_TOOLS, ToolScope.DELEGATES))
    assert "delegate_code_analyst" in kept
    assert "web_search" not in kept
    assert "python_exec" not in kept


def test_scope_never_leaves_a_turn_toolless():
    only_extended = _tools("semantic_search", "web_search")
    assert _names(scope_tools(only_extended, ToolScope.CORE)) == ["semantic_search", "web_search"]


def test_wants_delegates():
    assert wants_delegates(ToolScope.ALL)
    assert wants_delegates(ToolScope.DELEGATES)
    assert not wants_delegates(ToolScope.CORE)


def test_retrieval_none_unbinds_semantic_search():
    d = PolicyDecision(retrieval=RetrievalDepth.NONE)
    assert "semantic_search" not in _names(drop_disabled_tools(ALL_TOOLS, d))


def test_other_retrieval_depths_keep_semantic_search():
    for depth in (RetrievalDepth.SMALL, RetrievalDepth.LARGE, RetrievalDepth.DEFAULT):
        d = PolicyDecision(retrieval=depth)
        assert "semantic_search" in _names(drop_disabled_tools(ALL_TOOLS, d))


def test_drop_disabled_never_leaves_nothing():
    d = PolicyDecision(retrieval=RetrievalDepth.NONE)
    assert _names(drop_disabled_tools(_tools("semantic_search"), d)) == ["semantic_search"]


# ── memory axis ──────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("depth", "configured", "expected"),
    [
        (HistoryDepth.FULL, 12_000, 12_000),
        (HistoryDepth.SHORT, 12_000, SHORT_HISTORY_TOKENS),
        (HistoryDepth.SHORT, 1_000, 1_000),  # never more than configured
        (HistoryDepth.NONE, 12_000, 0),
    ],
)
def test_history_budget(depth, configured, expected):
    assert history_budget(depth, configured) == expected


def test_retrieval_k_mapping():
    assert retrieval_k(RetrievalDepth.DEFAULT) is None
    assert retrieval_k(RetrievalDepth.NONE) == 0
    assert retrieval_k(RetrievalDepth.SMALL) < retrieval_k(RetrievalDepth.LARGE)


def test_apply_to_install_copies_and_sets_the_retrieval_default():
    install = {"install_id": 1, "account_login": "acme"}
    out = apply_to_install(install, PolicyDecision(retrieval_k=4))
    assert out["_policy_retrieval_k"] == 4
    assert out["account_login"] == "acme"
    assert "_policy_retrieval_k" not in install  # input untouched
