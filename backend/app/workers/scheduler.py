"""Background scheduler — runs cron-style jobs without an external worker.

For a single-process deployment this is fine. When you scale to multiple
backend replicas, move these jobs to a dedicated worker process (e.g. Celery
beat, dramatiq, or a separate APScheduler instance with a Mongo job store)
so they don't run N times in parallel.

Current jobs:
  * sync_installations — every 30 min, refresh the installations list from
    GitHub (catches anything missed by webhooks during downtime).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.clients.github import list_installations
from app.core.db import get_db

log = logging.getLogger("dypol.scheduler")
_scheduler: AsyncIOScheduler | None = None


async def sync_installations() -> None:
    """Reconcile Mongo's view of installations with GitHub. Idempotent."""
    db = get_db()
    try:
        live = await list_installations()
    except Exception as exc:
        log.warning("sync_installations: list_installations failed: %s", exc)
        return

    now = datetime.now(timezone.utc)
    seen_ids: set[int] = set()
    for inst in live:
        account = inst.get("account") or {}
        seen_ids.add(inst["id"])
        await db["installations"].update_one(
            {"install_id": inst["id"]},
            {
                "$set": {
                    "install_id": inst["id"],
                    "account_login": (account.get("login") or "").lower(),
                    "account_type": account.get("type"),
                    "account_id": account.get("id"),
                    "repository_selection": inst.get("repository_selection"),
                    "permissions": inst.get("permissions") or {},
                    "events": inst.get("events") or [],
                    "suspended_at": inst.get("suspended_at"),
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
    # Mark anything not seen as deleted (App was uninstalled while we were
    # offline and we missed the webhook).
    #
    # ``$exists`` is load-bearing: $nin ALSO matches documents where the field
    # is missing, and public (open-source) workspaces carry no install_id — so
    # without this guard every public workspace was deleted on each run.
    if seen_ids:
        await db["installations"].delete_many(
            {"install_id": {"$exists": True, "$nin": list(seen_ids)}}
        )


async def rag_index_tick() -> None:
    """Incremental RAG indexing — drains dirty repos / backfills, tenant-scoped.

    Only scheduled when RAG is enabled. Heavy work lives in app/rag/ingest.py;
    this wrapper keeps the scheduler thin and swallows errors so one bad tick
    never stops the loop. Like ``sync_installations``, this must move to a
    single dedicated worker when scaling to multiple backend replicas, else
    each replica would re-embed in parallel.
    """
    try:
        from app.rag.ingest import run_index_tick

        result = await run_index_tick()
        if result:
            log.info("rag_index_tick: %s", result)
    except Exception as exc:
        log.warning("rag_index_tick failed: %s", exc)


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(
        sync_installations,
        "interval",
        minutes=30,
        id="sync_installations",
        next_run_time=datetime.now(timezone.utc),  # run once on startup
    )

    # Conditionally schedule incremental RAG indexing. Gated by is_rag_enabled()
    # so the job is absent entirely in pure-agentic mode.
    try:
        from app.core.config import get_settings
        from app.rag import is_rag_enabled

        if is_rag_enabled():
            _scheduler.add_job(
                rag_index_tick,
                "interval",
                minutes=get_settings().rag_index_interval_min,
                id="rag_index_tick",
                max_instances=1,
                coalesce=True,
            )
            log.info("scheduled rag_index_tick (RAG enabled)")
    except Exception as exc:
        log.warning("rag indexing not scheduled: %s", exc)

    _scheduler.start()


async def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        # let pending tasks settle
        await asyncio.sleep(0)
