"""Externally-triggered background jobs for serverless deployments.

Vercel has no long-lived process for APScheduler to live in, so the same jobs
are driven by this tick instead: UptimeRobot calls it every 5 minutes (with
``?key=``) and a daily Vercel Cron backs it up (with ``Authorization: Bearer``).
Each job keeps its own cadence — see ``run_due_jobs``.
"""
from __future__ import annotations

import hmac

from fastapi import APIRouter, Header, HTTPException, Query

from app.core.config import get_settings
from app.workers.scheduler import run_due_jobs

router = APIRouter(prefix="/cron", tags=["cron"])


def _authorized(secret: str, authorization: str | None, key: str | None) -> bool:
    supplied = key or ""
    if authorization and authorization.startswith("Bearer "):
        supplied = authorization.removeprefix("Bearer ")
    return bool(supplied) and hmac.compare_digest(supplied.encode(), secret.encode())


# HEAD too: uptime monitors commonly probe with HEAD rather than GET.
@router.api_route("/tick", methods=["GET", "HEAD"])
async def tick(
    authorization: str | None = Header(default=None),
    key: str | None = Query(default=None),
) -> dict[str, list[str]]:
    secret = get_settings().cron_secret
    if not secret:
        raise HTTPException(status_code=503, detail="CRON_SECRET is not configured")
    if not _authorized(secret, authorization, key):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return await run_due_jobs()
