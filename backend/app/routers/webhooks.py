"""GitHub webhook receiver.

GitHub POSTs every event for our App to ``/webhooks/github``. We:

  1. Verify the X-Hub-Signature-256 HMAC against ``GITHUB_APP_WEBHOOK_SECRET``.
  2. Dispatch by event type to update Mongo:
        - installation        → upsert/remove installations
        - installation_repositories → adjust repos in install
        - push / pull_request / pull_request_review / issues / issue_comment
                              → append to ``events`` collection (Activity feed)

The handler returns 200 fast — heavy aggregation runs in the sync worker.
"""
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from app.core.config import get_settings
from app.core.db import get_db

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _verify(secret: str, body: bytes, signature: str | None) -> bool:
    if not signature or not signature.startswith("sha256="):
        return False
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={digest}", signature)


@router.post("/github")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(...),
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
) -> dict:
    body = await request.body()
    secret = get_settings().github_app_webhook_secret
    if secret and not _verify(secret, body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="bad_signature")

    payload: dict[str, Any] = await request.json()
    handler = _DISPATCH.get(x_github_event)
    if handler is None:
        return {"ok": True, "ignored": x_github_event}
    await handler(payload)
    return {"ok": True}


# ──────────────────────────────────────────────────────────────────────
# Dispatchers
# ──────────────────────────────────────────────────────────────────────
async def _on_installation(payload: dict[str, Any]) -> None:
    """App installed / uninstalled / suspended on an account."""
    inst = payload.get("installation") or {}
    action = payload.get("action")
    install_id = inst.get("id")
    if not install_id:
        return

    db = get_db()
    if action == "deleted":
        await db["installations"].delete_one({"install_id": install_id})
        await db["install_tokens"].delete_one({"install_id": install_id})
        # Purge this tenant's RAG index (vector collection + bookkeeping) so no
        # orphaned embeddings remain after an uninstall. Best-effort + gated.
        try:
            from app.rag import is_rag_enabled

            if is_rag_enabled():
                from app.rag.state import clear_tenant

                await clear_tenant(install_id)
        except Exception:
            pass
        return

    account = inst.get("account") or {}
    repos = payload.get("repositories") or []
    doc = {
        "install_id": install_id,
        "account_login": (account.get("login") or "").lower(),
        "account_type": account.get("type"),
        "account_id": account.get("id"),
        "repository_selection": inst.get("repository_selection"),
        "repositories": [r["full_name"] for r in repos],
        "permissions": inst.get("permissions") or {},
        "events": inst.get("events") or [],
        "suspended_at": inst.get("suspended_at"),
        "updated_at": datetime.now(timezone.utc),
    }
    await db["installations"].update_one(
        {"install_id": install_id},
        {"$set": doc, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )


async def _on_installation_repositories(payload: dict[str, Any]) -> None:
    inst = payload.get("installation") or {}
    install_id = inst.get("id")
    if not install_id:
        return
    db = get_db()
    added = [r["full_name"] for r in payload.get("repositories_added") or []]
    removed = [r["full_name"] for r in payload.get("repositories_removed") or []]
    if added:
        await db["installations"].update_one(
            {"install_id": install_id},
            {"$addToSet": {"repositories": {"$each": added}}},
        )
    if removed:
        await db["installations"].update_one(
            {"install_id": install_id},
            {"$pullAll": {"repositories": removed}},
        )


async def _record_event(event: str, payload: dict[str, Any]) -> None:
    repo = (payload.get("repository") or {}).get("full_name", "")
    sender = payload.get("sender") or {}
    inst = payload.get("installation") or {}
    doc = {
        "event": event,
        "action": payload.get("action"),
        "repo": repo,
        "actor": sender.get("login"),
        "actor_avatar": sender.get("avatar_url"),
        "install_id": inst.get("id"),
        "payload": _slim_payload(event, payload),
        "created_at": datetime.now(timezone.utc),
    }
    await get_db()["events"].insert_one(doc)

    # Mark RAG index dirty so the scheduler re-embeds the changed content. Fast
    # (a flag write) — heavy embedding happens in rag_index_tick. Gated + fully
    # guarded so webhooks stay fast and never fail because of RAG.
    await _mark_rag_dirty(event, inst.get("id"), repo, payload)


async def _mark_rag_dirty(
    event: str, install_id: Any, repo: str, payload: dict[str, Any]
) -> None:
    """Flag changed code/prose for re-indexing. No-op unless RAG is enabled."""
    if not install_id or not repo:
        return
    try:
        from app.rag import is_rag_enabled

        if not is_rag_enabled():
            return
        from app.rag.state import mark_dirty

        if event == "push":
            await mark_dirty(install_id, repo, "code", payload.get("after") or "")
        elif event in {
            "pull_request",
            "pull_request_review",
            "pull_request_review_comment",
        }:
            num = (payload.get("pull_request") or {}).get("number")
            await mark_dirty(install_id, repo, "pr", str(num or ""))
        elif event in {"issues", "issue_comment"}:
            num = (payload.get("issue") or {}).get("number")
            await mark_dirty(install_id, repo, "issue", str(num or ""))
    except Exception:
        # RAG dirty-marking is best-effort; never let it affect webhook 200s.
        pass


def _slim_payload(event: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Keep only fields useful for an activity feed — full payloads are huge."""
    if event == "push":
        return {
            "ref": payload.get("ref"),
            "commits": len(payload.get("commits") or []),
            "head": (payload.get("head_commit") or {}).get("id"),
            "message": (payload.get("head_commit") or {}).get("message"),
        }
    if event in {"pull_request", "pull_request_review", "pull_request_review_comment"}:
        pr = payload.get("pull_request") or {}
        return {
            "number": pr.get("number"),
            "title": pr.get("title"),
            "url": pr.get("html_url"),
            "state": pr.get("state"),
            "merged": pr.get("merged"),
        }
    if event in {"issues", "issue_comment"}:
        issue = payload.get("issue") or {}
        return {
            "number": issue.get("number"),
            "title": issue.get("title"),
            "url": issue.get("html_url"),
            "state": issue.get("state"),
        }
    return {}


_DISPATCH = {
    "installation": _on_installation,
    "installation_repositories": _on_installation_repositories,
    "push": lambda p: _record_event("push", p),
    "pull_request": lambda p: _record_event("pull_request", p),
    "pull_request_review": lambda p: _record_event("pull_request_review", p),
    "pull_request_review_comment": lambda p: _record_event("pull_request_review_comment", p),
    "issues": lambda p: _record_event("issues", p),
    "issue_comment": lambda p: _record_event("issue_comment", p),
}
