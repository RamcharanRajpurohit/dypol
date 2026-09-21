"""Per-user daily API-call quota for chat turns.

A simple, tamper-resistant usage ceiling: each chat turn consumes one call
from a fixed UTC-day bucket. Every decision is made from the BACKEND's clock
and the BACKEND's counter (Mongo, atomically incremented) — a client that
lies about its local time, replays an old response, or races concurrent
requests cannot get more calls than the configured limit.

Design notes:
  * The day bucket key (``YYYY-MM-DD``) is derived from
    ``datetime.now(timezone.utc)`` on the SERVER. Nothing the client sends
    influences it — a forged/late/early client clock cannot shift the window
    or reset the count early.
  * ``consume()`` uses Mongo's atomic ``$inc`` conditioned on the counter
    staying below the limit, so two concurrent sends can never both claim
    the last remaining call (the loser is refused).
  * Enforcement fails OPEN on internal errors — quota must never be the
    reason the product is down, the same policy the token budget follows.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import get_settings
from app.core.db import get_db

log = logging.getLogger("dypol.quota")

COLL = "usage_calls"


def day_key(now: datetime | None = None) -> str:
    """UTC-day bucket for ``now`` (server clock). Never trust client time."""
    dt = now or datetime.now(UTC)
    return dt.strftime("%Y-%m-%d")


def day_limit() -> int:
    """Configured daily call limit; <= 0 means unlimited (quota disabled)."""
    return get_settings().daily_call_limit


def next_reset_utc(now: datetime | None = None) -> datetime:
    """The instant the current UTC-day bucket rolls over."""
    dt = now or datetime.now(UTC)
    tomorrow = (dt + timedelta(days=1)).strftime("%Y-%m-%d")
    return datetime.strptime(tomorrow, "%Y-%m-%d").replace(tzinfo=UTC)


def _quota_key(user_id: int) -> dict[str, Any]:
    # Scope: per USER (not per org) — one ceiling across every workspace,
    # matching how the LLM spend actually bills.
    return {"user_id": user_id, "day": day_key()}


async def status(user_id: int) -> tuple[int, int, datetime]:
    """Return (used_today, limit, next_reset_utc). Fails open as (0, limit, reset)."""
    try:
        doc = await get_db()[COLL].find_one(_quota_key(user_id))
        used = int((doc or {}).get("calls", 0))
        return used, day_limit(), next_reset_utc()
    except Exception as exc:
        log.warning("quota status read failed (reporting 0 used): %s", exc)
        return 0, day_limit(), next_reset_utc()


async def consume(user_id: int) -> bool:
    """Atomically claim one call from today's bucket. False when exhausted.

    ``$inc`` with a ``calls < limit`` filter is a single atomic
    compare-and-increment: the write only lands while the counter is still
    under the limit, so concurrent requests race safely — exactly one of
    them can claim the final remaining call.
    """
    limit = day_limit()
    if limit <= 0:
        return True  # quota disabled
    try:
        res = await get_db()[COLL].update_one(
            {**_quota_key(user_id), "calls": {"$lt": limit}},
            {"$inc": {"calls": 1}, "$set": {"updated_at": datetime.now(UTC)}},
            upsert=True,
        )
        if res.modified_count > 0:
            return True
        # The conditional write didn't land: either the counter reached the
        # limit, OR no doc exists yet (upsert with a non-matching filter is a
        # no-op, so the very first call of the day lands here). Seed the doc
        # if absent, then re-read: a count over the limit means refusal.
        await get_db()[COLL].update_one(
            _quota_key(user_id),
            {"$setOnInsert": {"calls": 0, "created_at": datetime.now(UTC)}},
            upsert=True,
        )
        doc = await get_db()[COLL].find_one(_quota_key(user_id))
        used = int((doc or {}).get("calls", 0))
        return used < limit
    except Exception as exc:
        log.warning("quota consume failed (allowing): %s", exc)
        return True


async def refund(user_id: int) -> None:
    """Give a claimed call back — used when a turn fails before doing work."""
    try:
        await get_db()[COLL].update_one(_quota_key(user_id), {"$inc": {"calls": -1}})
    except Exception as exc:
        log.warning("quota refund failed: %s", exc)
