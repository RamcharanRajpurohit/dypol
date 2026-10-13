"""Agent-run ledger — one durable row per agent turn with its cost and latency.

FUTURE_PLAN §8 Phase 1: "Add ``cost_usd`` and ``latency_ms`` to every trace
row". ``TraceCollector.usage_summary()`` already computes both in memory, but
they died with the request. This module persists them to ``agent_runs`` so
they can be (a) aggregated for the cost dashboard and (b) re-scored offline by
``app.telemetry.replay`` under a different policy.

Writes are best-effort: a ledger failure must never fail a user's turn.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.db import get_db

log = logging.getLogger("dypol.agent_runs")

COLLECTION = "agent_runs"

# Strong refs to in-flight ledger writes. ``asyncio.create_task`` only keeps a
# weak reference, so an un-referenced task can be garbage-collected mid-write.
_pending: set[asyncio.Task[None]] = set()


def _row(
    user_id: int,
    org: str,
    session_id: str,
    summary: dict[str, Any],
    model_calls: list[dict[str, Any]],
    wall_ms: int,
    path: str,
) -> dict[str, Any]:
    return {
        "_id": uuid.uuid4().hex,
        "user_id": user_id,
        "org": org,
        "session_id": session_id,
        "path": path,  # "sync" | "stream"
        "created_at": datetime.now(UTC),
        "wall_ms": wall_ms,
        "model_latency_ms": summary.get("latency_ms", 0),
        "cost_usd": summary.get("cost_usd", 0.0),
        "fully_priced": summary.get("fully_priced", True),
        "input_tokens": summary.get("input_tokens", 0),
        "output_tokens": summary.get("output_tokens", 0),
        "tool_calls": summary.get("tool_calls", 0),
        "model_calls": [
            {
                "model": m.get("model", ""),
                "label": m.get("label"),
                "input_tokens": m.get("input_tokens", 0),
                "output_tokens": m.get("output_tokens", 0),
                "cost_usd": m.get("cost_usd"),
                "duration_ms": m.get("duration_ms"),
            }
            for m in model_calls
        ],
    }


async def _insert(row: dict[str, Any]) -> None:
    try:
        await get_db()[COLLECTION].insert_one(row)
    except Exception as exc:
        log.warning("agent_runs: insert failed: %s", exc)


def record_run(
    user_id: int,
    org: str,
    session_id: str,
    summary: dict[str, Any],
    model_calls: list[dict[str, Any]],
    wall_ms: int,
    path: str = "sync",
) -> None:
    """Fire-and-forget persist so the ledger never adds latency to a turn."""
    row = _row(user_id, org, session_id, summary, model_calls, wall_ms, path)
    task = asyncio.create_task(_insert(row))
    _pending.add(task)
    task.add_done_callback(_pending.discard)


async def drain_pending() -> None:
    """Await in-flight ledger writes — call on shutdown so rows aren't lost."""
    if _pending:
        await asyncio.gather(*list(_pending), return_exceptions=True)


def _percentile(values: list[float], q: float) -> float:
    """Nearest-rank percentile; ``values`` need not be sorted."""
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(len(ordered) * q))
    return float(ordered[idx])


async def cost_summary(org: str, days: int = 7, user_id: int | None = None) -> dict[str, Any]:
    """Org (or single-user) cost + latency rollup over the last ``days`` days."""
    since = datetime.now(UTC) - timedelta(days=days)
    query: dict[str, Any] = {"org": org, "created_at": {"$gte": since}}
    if user_id is not None:
        query["user_id"] = user_id

    rows = [r async for r in get_db()[COLLECTION].find(query)]
    costs = [r.get("cost_usd") or 0.0 for r in rows]
    latencies = [r.get("wall_ms") or 0 for r in rows]

    by_model: dict[str, dict[str, float]] = {}
    for r in rows:
        for m in r.get("model_calls", []):
            agg = by_model.setdefault(m["model"], {"calls": 0, "cost_usd": 0.0, "tokens": 0})
            agg["calls"] += 1
            agg["cost_usd"] += m.get("cost_usd") or 0.0
            agg["tokens"] += m.get("input_tokens", 0) + m.get("output_tokens", 0)

    total = sum(costs)
    return {
        "org": org,
        "days": days,
        "turns": len(rows),
        "total_cost_usd": round(total, 6),
        "mean_cost_usd": round(total / len(rows), 6) if rows else 0.0,
        "p50_cost_usd": _percentile(costs, 0.50),
        "p95_cost_usd": _percentile(costs, 0.95),
        "p50_latency_ms": _percentile(latencies, 0.50),
        "p95_latency_ms": _percentile(latencies, 0.95),
        # Turns containing a call we had no rate for: their cost_usd is a lower
        # bound, so every total above is too whenever this is non-zero.
        "unpriced_turns": sum(1 for r in rows if not r.get("fully_priced", True)),
        "by_model": by_model,
    }


MAX_REPLAY_RUNS = 20_000


async def iter_runs(org: str, limit: int = 5_000) -> list[dict[str, Any]]:
    """Most recent runs for an org — the input to an offline replay."""
    limit = max(1, min(limit, MAX_REPLAY_RUNS))
    cursor = (
        get_db()[COLLECTION]
        .find({"org": org}, {"model_calls": 1})
        .sort("created_at", -1)
        .limit(limit)
    )
    return [r async for r in cursor]
