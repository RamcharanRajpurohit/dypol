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
