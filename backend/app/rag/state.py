"""Mongo bookkeeping for the index pipeline.

Two collections:
  * ``rag_index_state`` — one ``IndexCursor`` per (install_id, repo). Lets
    the scheduler resume where it left off and skip unchanged repos.
  * ``rag_dirty``       — a coalescing work queue. Webhooks (push/PR/issue)
    mark a (repo, kind, ref) dirty; the index tick drains it. Unique-ish on
    the tuple so repeated events collapse to one row.

All functions use ``get_db()`` and are tenant-scoped by ``install_id``.
"""
from __future__ import annotations

import contextlib
import logging
from datetime import UTC, datetime
from typing import Any

from app.core.db import get_db
from app.rag.models import IndexCursor

log = logging.getLogger("dypol.rag.state")

_STATE = "rag_index_state"
_DIRTY = "rag_dirty"


# ──────────────────────────────────────────────────────────────────────
# Index cursors
# ──────────────────────────────────────────────────────────────────────
async def get_cursor(install_id: int, repo: str) -> IndexCursor | None:
    db = get_db()
    doc = await db[_STATE].find_one({"install_id": install_id, "repo": repo})
    return IndexCursor.from_doc(doc) if doc else None


async def set_cursor(cursor: IndexCursor) -> None:
    db = get_db()
    cursor.last_indexed_at = datetime.now(UTC)
    await db[_STATE].update_one(
        {"install_id": cursor.install_id, "repo": cursor.repo},
        {"$set": cursor.to_doc()},
        upsert=True,
    )


async def list_cursors(install_id: int) -> list[IndexCursor]:
    db = get_db()
    out: list[IndexCursor] = []
    async for doc in db[_STATE].find({"install_id": install_id}):
        out.append(IndexCursor.from_doc(doc))
    return out


# ──────────────────────────────────────────────────────────────────────
# Dirty queue
# ──────────────────────────────────────────────────────────────────────
async def mark_dirty(
    install_id: int, repo: str, kind: str, ref: str | None = None
) -> None:
    """Enqueue a (repo, kind, ref) for re-indexing. Coalesces duplicates."""
    db = get_db()
    ref = ref or ""
    await db[_DIRTY].update_one(
        {"install_id": install_id, "repo": repo, "kind": kind, "ref": ref},
        {
            "$set": {
                "install_id": install_id,
                "repo": repo,
                "kind": kind,
                "ref": ref,
                "queued_at": datetime.now(UTC),
            }
        },
        upsert=True,
    )


async def drain_dirty(install_id: int, limit: int = 50) -> list[dict[str, Any]]:
    """Pop up to ``limit`` dirty entries for an install (oldest first),
    removing them as they're returned so they aren't re-processed."""
    db = get_db()
    out: list[dict[str, Any]] = []
    cursor = (
        db[_DIRTY]
        .find({"install_id": install_id})
        .sort("queued_at", 1)
        .limit(limit)
    )
    async for doc in cursor:
        out.append(doc)
    if out:
        ids = [d["_id"] for d in out]
        await db[_DIRTY].delete_many({"_id": {"$in": ids}})
    return out


async def has_dirty(install_id: int) -> bool:
    db = get_db()
    return (
        await db[_DIRTY].find_one({"install_id": install_id}, {"_id": 1})
    ) is not None


# ──────────────────────────────────────────────────────────────────────
# Tenant teardown
# ──────────────────────────────────────────────────────────────────────
async def clear_tenant(install_id: int) -> None:
    """Wipe everything for an install: the vector collection + all rag_* docs.
    Best-effort — a missing vector collection is fine (uninstall path)."""
    # Drop the vector store collection first (it's outside Mongo).
    try:
        from app.rag.store import get_vector_store

        store = get_vector_store(install_id)
        # Chroma: drop the whole per-tenant collection if we can.
        client = getattr(store, "_client", None)
        if client is not None and hasattr(client, "delete_collection"):
            with contextlib.suppress(Exception):
                client.delete_collection(name=f"tenant_{install_id}")
    except Exception as exc:
        log.info("clear_tenant: vector store cleanup skipped: %s", exc)

    db = get_db()
    await db[_STATE].delete_many({"install_id": install_id})
    await db[_DIRTY].delete_many({"install_id": install_id})
