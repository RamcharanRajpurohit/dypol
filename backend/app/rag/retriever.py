"""Hybrid retrieval (vector + BM25, RRF-fused) and the semantic_search tool.

Retrieval mirrors what production code-search systems do: a dense vector
query for semantic recall, a sparse BM25 pass over the same candidate pool
for exact-term precision, fused with Reciprocal Rank Fusion (RRF), then a
small boost when query tokens appear verbatim as a symbol name or in the
path. The result is a ranked list of POINTERS — the agent is told to call
``github_get`` for authoritative current content.

At import time this module registers its factory on ``chat_tools`` so the
agent gains a ``semantic_search`` tool *only* when ``is_rag_enabled()`` —
otherwise the factory returns None and the tool is never advertised.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from app.core.config import get_settings
from app.rag.embeddings import get_embedder
from app.rag.models import RetrievedChunk
from app.rag.store import get_vector_store

log = logging.getLogger("dypol.rag.retriever")

_RRF_K = 60  # standard RRF damping constant
# Pull a generous candidate pool so BM25 has something to rank over.
_CANDIDATE_POOL = 200
_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]+")


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def _rrf(rank: int) -> float:
    return 1.0 / (_RRF_K + rank)


async def hybrid_search(
    tenant_id: int,
    query: str,
    kind: str = "any",
    repo: str | None = None,
    k: int | None = None,
) -> list[RetrievedChunk]:
    """Vector + BM25 → RRF → identifier boost. Returns top-k RetrievedChunks.

    Empty list if there's no embedder or nothing indexed. Never raises.
    """
    if not query or not query.strip():
        return []
    s = get_settings()
    top_k = k or s.rag_retrieval_k

    embed_kind = "code" if kind == "code" else "prose"
    embedder = get_embedder(embed_kind)
    if embedder is None:
        # Fall back to the other kind's embedder if the requested one is off.
        embedder = get_embedder("prose") or get_embedder("code")
    if embedder is None:
        return []

    try:
        store = get_vector_store(tenant_id)
    except Exception as exc:
        log.info("hybrid_search: store unavailable: %s", exc)
        return []

    where: dict[str, Any] = {}
    if repo:
        where["repo"] = repo
    if kind in ("code", "prose"):
        where["kind"] = kind

    # ── Vector pass ────────────────────────────────────────────────
    try:
        qvec = (await asyncio.to_thread(embedder.embed, [query]))[0]
    except Exception as exc:
        log.info("hybrid_search: query embed failed: %s", exc)
        return []

    try:
        vec_hits = await asyncio.to_thread(
            store.query, qvec, max(top_k * 4, _CANDIDATE_POOL // 4), where or None
        )
    except Exception as exc:
        log.info("hybrid_search: vector query failed: %s", exc)
        vec_hits = []

    # ── BM25 candidate pool ────────────────────────────────────────
    pool = await _candidate_pool(store, where, vec_hits)
    if not pool:
        # No pool to fuse over — return the vector hits as-is.
        return _to_retrieved(vec_hits, top_k)

    bm25_ranks = _bm25_rank(query, pool)

    # ── Reciprocal Rank Fusion ─────────────────────────────────────
    # id → fused score; build a metadata map alongside.
    meta_by_id: dict[str, dict[str, Any]] = {pid: md for pid, _doc, md in pool}
    text_by_id: dict[str, str] = {pid: doc for pid, doc, _md in pool}
    fused: dict[str, float] = {}

    for rank, (pid, _score, md) in enumerate(vec_hits):
        fused[pid] = fused.get(pid, 0.0) + _rrf(rank)
        meta_by_id.setdefault(pid, md)
        text_by_id.setdefault(pid, md.get("text", ""))

    for rank, pid in enumerate(bm25_ranks):
        fused[pid] = fused.get(pid, 0.0) + _rrf(rank)

    # ── Identifier boost ───────────────────────────────────────────
    q_tokens = set(_tokenize(query))
    for pid in list(fused.keys()):
        md = meta_by_id.get(pid, {})
        symbol = (md.get("symbol") or "").lower()
        path = (md.get("path") or "").lower()
        if symbol and symbol in q_tokens:
            fused[pid] += 0.5  # strong: exact symbol hit
        elif q_tokens & set(_tokenize(path)):
            fused[pid] += 0.15  # weaker: path token overlap

    ranked = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:top_k]

    out: list[RetrievedChunk] = []
    for pid, fscore in ranked:
        md = meta_by_id.get(pid, {})
        text = text_by_id.get(pid) or md.get("text", "")
        out.append(_md_to_retrieved(text, fscore, md))
    return out


async def _candidate_pool(
    store: Any, where: dict[str, Any], vec_hits: list[tuple[str, float, dict]]
) -> list[tuple[str, str, dict[str, Any]]]:
    """Build the (id, text, metadata) pool BM25 ranks over.

    Prefer pulling the tenant's docs directly (Chroma ``all_docs``); fall
    back to the vector hits when that helper isn't available."""
    if hasattr(store, "all_docs"):
        try:
            pool = await asyncio.to_thread(
                store.all_docs, where or None, _CANDIDATE_POOL
            )
            if pool:
                return pool
        except Exception as exc:
            log.debug("candidate pool via all_docs failed: %s", exc)
    # Fallback: use vector hits' own text/metadata.
    return [
        (pid, md.get("text", ""), md) for pid, _score, md in vec_hits if md
    ]


def _bm25_rank(query: str, pool: list[tuple[str, str, dict]]) -> list[str]:
    """Return pool ids ordered by BM25 relevance (best first). Lazy import."""
    try:
        from rank_bm25 import BM25Okapi
    except Exception:
        return []
    corpus = [_tokenize(doc) for _pid, doc, _md in pool]
    if not any(corpus):
        return []
    try:
        bm25 = BM25Okapi(corpus)
        scores = bm25.get_scores(_tokenize(query))
    except Exception:
        return []
    order = sorted(range(len(pool)), key=lambda i: scores[i], reverse=True)
    return [pool[i][0] for i in order]


def _to_retrieved(
    hits: list[tuple[str, float, dict[str, Any]]], top_k: int
) -> list[RetrievedChunk]:
    out: list[RetrievedChunk] = []
    for _pid, score, md in hits[:top_k]:
        text = md.get("text", "")
        out.append(_md_to_retrieved(text, score, md))
    return out


def _md_to_retrieved(
    text: str, score: float, md: dict[str, Any]
) -> RetrievedChunk:
    return RetrievedChunk(
        text=text,
        kind=md.get("kind", "code"),
        repo=md.get("repo", ""),
        score=float(score),
        source_url=md.get("url", "") or "",
        path=md.get("path"),
        start_line=md.get("start_line"),
        end_line=md.get("end_line"),
        symbol=md.get("symbol"),
        lang=md.get("lang"),
        sha=md.get("sha"),
        ref_number=md.get("ref_number"),
        url=md.get("url"),
    )


# ──────────────────────────────────────────────────────────────────────
# Tool factory — wired into chat_tools at import time.
# ──────────────────────────────────────────────────────────────────────
def semantic_search_handler_factory(install: dict[str, Any]):
    """Return an async ``semantic_search`` handler, or None when RAG is off.

    The handler shapes results into a frontend-friendly pointer list and
    runs them through ``_truncate`` to respect the per-tool byte cap.
    """
    from app.rag import is_rag_enabled

    if not is_rag_enabled():
        return None

    # Works for BOTH modes: install workspaces namespace on their install id,
    # public workspaces on their (negated) account id. See app/rag/tenant.py.
    from app.rag.tenant import tenant_id_for

    tenant_id = tenant_id_for(install)
    if tenant_id is None:
        return None

    from app.services.chat_tools import _truncate

    async def semantic_search(
        query: str,
        kind: str = "any",
        repo: str | None = None,
        k: int | None = None,
    ) -> Any:
        try:
            results = await hybrid_search(
                tenant_id,
                query,
                kind=kind,
                repo=repo,
                k=k or get_settings().rag_retrieval_k,
            )
        except Exception as exc:
            return {"error": "semantic_search_failed", "message": str(exc)}

        shaped = []
        for r in results:
            lines = None
            if r.start_line is not None:
                lines = (
                    f"{r.start_line}-{r.end_line}"
                    if r.end_line and r.end_line != r.start_line
                    else str(r.start_line)
                )
            shaped.append(
                {
                    "kind": r.kind,
                    "repo": r.repo,
                    "path": r.path,
                    "lines": lines,
                    "symbol": r.symbol,
                    "number": r.ref_number,
                    "score": round(r.score, 4),
                    "snippet": (r.text or "")[:300],
                    "url": r.source_url or r.url,
                    "sha": r.sha,
                }
            )
        return _truncate(
            {
                "results": shaped,
                "count": len(shaped),
                "note": (
                    "Pointers only — call github_get for authoritative "
                    "current content."
                ),
            }
        )

    return semantic_search


# ──────────────────────────────────────────────────────────────────────
# Register with chat_tools at import time (graceful, never fatal).
# ──────────────────────────────────────────────────────────────────────
try:  # pragma: no cover - import-time wiring
    from app.services import chat_tools as _chat_tools

    _chat_tools.SEMANTIC_SEARCH_HANDLER_FACTORY = semantic_search_handler_factory
except Exception as _exc:  # pragma: no cover
    log.warning("could not register semantic_search factory: %s", _exc)
