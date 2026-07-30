"""Activity feed.

Two sources, picked per workspace:

  * **Install workspaces** — the ``events`` collection, written in real time
    by the webhook receiver (``routers/webhooks.py``). Lowest latency and
    covers private repos.
  * **Public workspaces** — GitHub's public events timeline
    (``/orgs/{org}/events`` or ``/users/{login}/events/public``). There is no
    App installation, so GitHub has nowhere to deliver webhooks; polling is
    the only option. Slightly delayed (GitHub caches this feed ~60s) and
    public repos only, but it means the feed is populated instead of empty.

An install workspace whose webhook feed is still empty (fresh install, no
pushes yet) also falls back to polling, so the tab is never blank when
GitHub has something to show.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.clients.github import gh_for
from app.core.db import get_db
from app.models.schemas import ActivityEvent
from app.services import cache

_TYPE_SUMMARIES = {
    "push": "pushed to",
    "pull_request": "PR",
    "pull_request_review": "reviewed PR",
    "pull_request_review_comment": "commented on PR",
    "issues": "issue",
    "issue_comment": "commented on issue",
    "release": "released",
    "fork": "forked",
    "watch": "starred",
    "create": "created",
    "delete": "deleted",
}

# GitHub's events timeline uses *Event class names; the webhook receiver (and
# therefore ``_summarize``) uses the hook names. Map one onto the other so both
# sources render identically.
_PUBLIC_EVENT_TYPES = {
    "PushEvent": "push",
    "PullRequestEvent": "pull_request",
    "PullRequestReviewEvent": "pull_request_review",
    "PullRequestReviewCommentEvent": "pull_request_review_comment",
    "IssuesEvent": "issues",
    "IssueCommentEvent": "issue_comment",
    "ReleaseEvent": "release",
    "ForkEvent": "fork",
    "WatchEvent": "watch",
    "CreateEvent": "create",
    "DeleteEvent": "delete",
}

_PUBLIC_EVENTS_TTL = 60  # GitHub caches this feed ~60s; polling faster is waste


def _summarize(event: str, payload: dict[str, Any], action: str | None) -> str:
    """Render one feed line. Every field is optional: the *anonymous* events
    timeline ships slimmed payloads (a PushEvent carries no commit list, a
    PullRequestEvent's nested PR has no title), so anything missing is simply
    left out rather than rendered as "0 commits" or "— None"."""
    base = _TYPE_SUMMARIES.get(event, event)
    if event == "push":
        ref = (payload.get("ref") or "").rsplit("/", 1)[-1]
        count = payload.get("commits")
        suffix = f" ({count} commits)" if count is not None else ""
        return f"{base} {ref}{suffix}".replace("  ", " ").strip()
    if event in {
        "pull_request",
        "pull_request_review",
        "pull_request_review_comment",
        "issues",
        "issue_comment",
    }:
        number = payload.get("number")
        title = (payload.get("title") or "").strip()
        line = f"{base} #{number}" if number else base
        if title:
            line += f" — {title}"
        return line + (f" ({action})" if action else "")
    if event == "release":
        return f"{base} {payload.get('title') or ''}".rstrip()
    if event in {"create", "delete"}:
        return f"{base} {payload.get('ref_type') or ''} {payload.get('ref') or ''}".rstrip()
    return base


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


# ──────────────────────────────────────────────────────────────────
# Source 1 — webhook feed (Mongo)
# ──────────────────────────────────────────────────────────────────
async def _events_from_webhooks(install_id: int, limit: int) -> list[ActivityEvent]:
    db = get_db()
    cursor = (
        db["events"]
        .find({"install_id": install_id})
        .sort("created_at", -1)
        .limit(limit)
    )
    events: list[ActivityEvent] = []
    async for doc in cursor:
        events.append(
            ActivityEvent(
                id=str(doc.get("_id")),
                type=doc.get("event", "unknown"),
                actor=doc.get("actor") or "?",
                actor_avatar=doc.get("actor_avatar") or "",
                repo=doc.get("repo", ""),
                summary=_summarize(
                    doc.get("event", ""), doc.get("payload") or {}, doc.get("action")
                ),
                created_at=_parse_dt(doc.get("created_at")),
            )
        )
    return events


# ──────────────────────────────────────────────────────────────────
# Source 2 — GitHub public events timeline (polled)
# ──────────────────────────────────────────────────────────────────
def _slim_public_payload(event: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Reshape a timeline payload into the same fields ``_summarize`` reads
    from webhook payloads."""
    if event == "push":
        # ``size`` is authoritative; ``commits`` is capped at 20 and absent
        # entirely on the anonymous timeline — leave the count out if neither
        # is present rather than claiming zero.
        count = payload.get("size")
        if count is None and payload.get("commits") is not None:
            count = len(payload["commits"])
        return {"ref": payload.get("ref"), "commits": count}
    if event in {"pull_request", "pull_request_review", "pull_request_review_comment"}:
        pr = payload.get("pull_request") or {}
        return {
            "number": pr.get("number") or payload.get("number"),
            "title": pr.get("title"),
        }
    if event in {"issues", "issue_comment"}:
        issue = payload.get("issue") or {}
        return {"number": issue.get("number"), "title": issue.get("title")}
    if event == "release":
        rel = payload.get("release") or {}
        return {"title": rel.get("name") or rel.get("tag_name")}
    if event in {"create", "delete"}:
        return {"ref_type": payload.get("ref_type"), "ref": payload.get("ref")}
    return {}


def _from_public_event(raw: dict[str, Any]) -> ActivityEvent | None:
    event = _PUBLIC_EVENT_TYPES.get(raw.get("type") or "")
    if event is None:
        return None  # MemberEvent, GollumEvent, … — not worth a feed row
    actor = raw.get("actor") or {}
    payload = raw.get("payload") or {}
    return ActivityEvent(
        id=str(raw.get("id")),
        type=event,
        actor=actor.get("login") or "?",
        actor_avatar=actor.get("avatar_url") or "",
        repo=(raw.get("repo") or {}).get("name", ""),
        summary=_summarize(event, _slim_public_payload(event, payload), payload.get("action")),
        created_at=_parse_dt(raw.get("created_at")),
    )


async def _events_from_github(
    install_id: int | None, org_login: str, account_type: str | None, limit: int
) -> list[ActivityEvent]:
    key = f"events:timeline:{org_login.lower()}:{limit}"
    if (cached := cache.get(key)) is not None:
        return cached

    path = (
        f"/users/{org_login}/events/public"
        if (account_type or "Organization") == "User"
        else f"/orgs/{org_login}/events"
    )
    try:
        raw = await gh_for(install_id).collect(
            path, params={"per_page": min(limit, 100)}, max_pages=1
        )
    except Exception:
        # Personal account under an org path, suspended org, rate limit —
        # an empty feed beats a failed page.
        return []

    events = [e for e in (_from_public_event(r) for r in raw) if e is not None][:limit]
    cache.set_(key, events, _PUBLIC_EVENTS_TTL)
    return events


# ──────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────
async def list_org_events(install: dict[str, Any], limit: int = 50) -> list[ActivityEvent]:
    """Recent activity for a workspace, from whichever source it has."""
    install_id = install.get("install_id")
    org_login = install.get("account_login") or ""
    account_type = install.get("account_type")

    if install_id is not None:
        events = await _events_from_webhooks(install_id, limit)
        if events:
            return events
        # Fresh install — no webhook has landed yet. Poll so the tab isn't
        # blank; the installation token makes this essentially free.

    if not org_login:
        return []
    return await _events_from_github(install_id, org_login, account_type, limit)
