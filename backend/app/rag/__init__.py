"""Hybrid RAG / semantic-search layer for DyPol AI — OPTIONAL at every layer.

Design (research-grounded): the agentic path (live GitHub API + search) is
PRIMARY. This package adds a *complementary* vector index queried just-in-time
via the ``semantic_search`` tool — exactly the hybrid model Claude Code uses.
It must never block boot: if RAG is disabled, its deps are missing, or no
embedder is configured, ``is_rag_enabled()`` returns False and the agent runs
in pure-agentic mode.

``is_rag_enabled()`` is the single source of truth, checked by:
  * ``services/chat_tools`` (register the semantic_search handler?)
  * ``agents/tools``        (advertise the tool to the model?)
  * ``workers/scheduler``   (schedule the incremental index job?)
"""
from __future__ import annotations

import logging

from app.core.config import get_settings

log = logging.getLogger("dypol.rag")

# Cache the gate result so we don't re-probe imports / embedders every call.
_enabled_cache: bool | None = None


def _deps_present() -> bool:
    """True if the lightweight RAG core deps import cleanly. Lazy — a missing
    optional dep degrades to pure-agentic instead of crashing the app."""
    import importlib.util

    for mod in ("chromadb", "tree_sitter", "tree_sitter_language_pack", "rank_bm25"):
        if importlib.util.find_spec(mod) is None:
            log.info("rag disabled: dependency %r not installed", mod)
            return False
    return True


def is_rag_enabled() -> bool:
    """Master gate. True only when RAG_ENABLED is set, the deps import, and at
    least one embedder resolves. Result is memoized for the process."""
    global _enabled_cache
    if _enabled_cache is not None:
        return _enabled_cache

    s = get_settings()
    if not s.rag_enabled:
        _enabled_cache = False
        return False

    if not _deps_present():
        _enabled_cache = False
        return False

    # An embedder must be resolvable, else there is nothing to index/query.
    try:
        from app.rag.embeddings import any_embedder_available

        if not any_embedder_available():
            log.info("rag disabled: no embedding provider/key available")
            _enabled_cache = False
            return False
    except Exception as exc:  # never let a probe crash the gate
        log.info("rag disabled: embedder probe failed: %s", exc)
        _enabled_cache = False
        return False

    _enabled_cache = True
    return True


def reset_enabled_cache() -> None:
    """Test/debug helper — force ``is_rag_enabled()`` to re-probe."""
    global _enabled_cache
    _enabled_cache = None
