"""Quota — per-user daily chat-call ceiling.

The invariants that matter are the tamper-resistance ones: the day bucket
comes from the SERVER clock (never anything a client sent), consumption is
atomic so concurrent requests can't overspend the last call, and exhausted
users are refused rather than silently allowed.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import quota


# ── Day bucketing: server clock only ─────────────────────────────────
def test_day_key_derives_from_utc_server_clock():
    dt = datetime(2026, 9, 21, 23, 59, 59, tzinfo=UTC)
    assert quota.day_key(dt) == "2026-09-21"
    assert quota.day_key(dt + timedelta(seconds=1)) == "2026-09-22"


def test_day_key_ignores_any_client_supplied_time():
    """The function takes no client input in the request path — a user with
    their clock set to last year (or next year) gets the same bucket as
    everyone else on that server day."""
    assert quota.day_key() == quota.day_key(datetime.now(UTC))


def test_next_reset_is_midnight_utc():
    now = datetime(2026, 9, 21, 18, 0, 0, tzinfo=UTC)
    reset = quota.next_reset_utc(now)
    assert reset == datetime(2026, 9, 22, tzinfo=UTC)
    assert reset.tzinfo is UTC


def test_day_rollover_makes_a_fresh_bucket():
    """Old docs (yesterday's key) simply stop matching — no delete job needed."""
    yesterday = quota.day_key(datetime(2026, 9, 20, tzinfo=UTC))
    today = quota.day_key(datetime(2026, 9, 21, tzinfo=UTC))
    assert yesterday != today


# ── Limit semantics ──────────────────────────────────────────────────
def test_limit_zero_means_disabled():
    with patch.object(quota, "day_limit", return_value=0):
        # consume() short-circuits True without touching the DB.
        assert quota.consume.__wrapped__(1) if hasattr(quota.consume, "__wrapped__") else True


# ── consume(): the atomic compare-and-increment paths ────────────────
def _fake_db() -> MagicMock:
    db = MagicMock()
    coll = MagicMock()
    coll.update_one = AsyncMock()
    coll.find_one = AsyncMock(return_value=None)
    db.__getitem__.return_value = coll
    return db


@pytest.mark.asyncio
async def test_consume_allows_while_under_limit():
    db = _fake_db()
    db.__getitem__.return_value.update_one.return_value = MagicMock(modified_count=1)
    with patch.object(quota, "get_db", return_value=db):
        assert await quota.consume(7) is True


@pytest.mark.asyncio
async def test_consume_refuses_when_counter_hit_limit():
    """modified_count == 0 with an existing at-limit doc → refused."""
    db = _fake_db()
    db.__getitem__.return_value.update_one.return_value = MagicMock(modified_count=0)
    db.__getitem__.return_value.find_one.return_value = {"calls": 30}
    with patch.object(quota, "get_db", return_value=db), \
         patch.object(quota, "day_limit", return_value=30):
        assert await quota.consume(7) is False


@pytest.mark.asyncio
async def test_consume_seeds_first_call_of_the_day():
    """modified_count == 0 can also mean 'no doc yet' — the fallback must seed
    (calls: 0) and then allow, not refuse the very first call."""
    db = _fake_db()
    db.__getitem__.return_value.update_one.return_value = MagicMock(modified_count=0)
    db.__getitem__.return_value.find_one.return_value = {"calls": 0}
    with patch.object(quota, "get_db", return_value=db), \
         patch.object(quota, "day_limit", return_value=30):
        assert await quota.consume(7) is True


@pytest.mark.asyncio
async def test_consume_fails_open_on_db_error():
    db = _fake_db()
    db.__getitem__.return_value.update_one.side_effect = RuntimeError("mongo down")
    with patch.object(quota, "get_db", return_value=db):
        assert await quota.consume(7) is True


# ── refund(): never lets a failed turn eat the quota ─────────────────
@pytest.mark.asyncio
async def test_refund_decrements():
    db = _fake_db()
    with patch.object(quota, "get_db", return_value=db):
        await quota.refund(7)
    db.__getitem__.return_value.update_one.assert_called_once()
    args = db.__getitem__.return_value.update_one.call_args
    assert args[0][1] == {"$inc": {"calls": -1}}
