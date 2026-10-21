"""The /cron/tick gate and the in-process scheduler switch (serverless)."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.routers import cron


@pytest.fixture
def client(monkeypatch):
    async def fake_run_due_jobs():
        return {"ran": ["sync_installations"], "skipped": [], "failed": []}

    monkeypatch.setattr(cron, "run_due_jobs", fake_run_due_jobs)
    app = FastAPI()
    app.include_router(cron.router)
    return TestClient(app)


@pytest.fixture
def secret(monkeypatch):
    monkeypatch.setattr(get_settings(), "cron_secret", "s3cret")
    return "s3cret"


def test_tick_refuses_when_no_secret_is_configured(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "cron_secret", None)
    assert client.get("/cron/tick?key=anything").status_code == 503


def test_tick_rejects_a_wrong_or_missing_key(client, secret):
    assert client.get("/cron/tick").status_code == 401
    assert client.get("/cron/tick?key=nope").status_code == 401
    assert client.get("/cron/tick", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_tick_accepts_query_key_and_vercel_bearer(client, secret):
    by_query = client.get(f"/cron/tick?key={secret}")
    assert by_query.status_code == 200
    assert by_query.json()["ran"] == ["sync_installations"]
    by_header = client.get("/cron/tick", headers={"Authorization": f"Bearer {secret}"})
    assert by_header.status_code == 200


def test_tick_answers_head_probes(client, secret):
    assert client.head(f"/cron/tick?key={secret}").status_code == 200


def test_in_process_scheduler_is_off_on_vercel(monkeypatch):
    monkeypatch.delenv("SCHEDULER_IN_PROCESS", raising=False)
    monkeypatch.setenv("VERCEL", "1")
    assert Settings().scheduler_in_process is False
    monkeypatch.delenv("VERCEL")
    assert Settings().scheduler_in_process is True


def test_health_answers_head_probes(monkeypatch):
    from app.routers import health

    class _Admin:
        async def command(self, _):
            return {"ok": 1}

    class _Client:
        admin = _Admin()

    monkeypatch.setattr(health, "get_client", lambda: _Client())
    monkeypatch.setattr(health, "get_app_jwt", lambda: "jwt")
    app = FastAPI()
    app.include_router(health.router)
    assert TestClient(app).head("/health").status_code == 200


class _FakeRuns:
    """Just enough of a Motor collection for ``run_due_jobs``' two queries."""

    def __init__(self):
        self.docs: dict[str, dict] = {}

    @staticmethod
    def _cond(doc, cond):
        ((field, op),) = cond.items()
        if "$exists" in op:
            return (field in doc) == op["$exists"]
        return field in doc and doc[field] <= op["$lte"]

    async def find_one_and_update(self, flt, update, upsert=False):
        from pymongo.errors import DuplicateKeyError

        doc = self.docs.get(flt["_id"])
        if doc is None:
            self.docs[flt["_id"]] = {"_id": flt["_id"], **update["$set"]}
            return None
        if all(any(self._cond(doc, c) for c in group["$or"]) for group in flt["$and"]):
            doc.update(update["$set"])
            return doc
        raise DuplicateKeyError("E11000")

    async def update_one(self, flt, update):
        doc = self.docs.get(flt["_id"])
        if doc is None or any(doc.get(k) != v for k, v in flt.items() if k != "_id"):
            return
        doc.update(update["$set"])
        for k in update["$unset"]:
            doc.pop(k, None)


@pytest.fixture
def ticking(monkeypatch):
    from datetime import timedelta

    from app.workers import scheduler

    runs = _FakeRuns()
    calls: list[str] = []

    async def job():
        calls.append("job")

    monkeypatch.setattr(scheduler, "get_db", lambda: {"scheduler_runs": runs})
    monkeypatch.setattr(
        scheduler, "_tick_jobs", lambda: [("job", job, timedelta(minutes=30))]
    )
    return scheduler, runs, calls


async def test_a_job_runs_once_per_interval(ticking):
    from datetime import timedelta

    scheduler, runs, calls = ticking
    assert (await scheduler.run_due_jobs())["ran"] == ["job"]
    assert (await scheduler.run_due_jobs())["skipped"] == ["job"]
    assert calls == ["job"]
    assert "lease_until" not in runs.docs["job"]
    runs.docs["job"]["last_run_at"] -= timedelta(minutes=31)
    assert (await scheduler.run_due_jobs())["ran"] == ["job"]
    assert calls == ["job", "job"]


async def test_a_stale_tick_cannot_release_a_lease_it_lost(ticking, monkeypatch):
    from datetime import UTC, datetime, timedelta

    scheduler, runs, calls = ticking
    newer_lease = datetime.now(UTC) + timedelta(minutes=10)

    async def slow_job():
        # Our lease expires mid-job and another tick takes the job over.
        runs.docs["job"].update(lease_token="newer", lease_until=newer_lease)

    monkeypatch.setattr(
        scheduler, "_tick_jobs", lambda: [("job", slow_job, timedelta(minutes=30))]
    )
    await scheduler.run_due_jobs()
    assert runs.docs["job"]["lease_token"] == "newer"
    assert runs.docs["job"]["lease_until"] == newer_lease
    assert "last_run_at" not in runs.docs["job"]
