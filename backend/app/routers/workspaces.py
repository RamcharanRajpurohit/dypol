"""Workspace management — discovering and adding public-org workspaces.

Install workspaces come from the GitHub App webhook (see ``webhooks.py``).
Public workspaces are added explicitly by the user from the UI: they search
for a GitHub org/user, we verify it exists and is public, then store a row
in the ``installations`` collection with ``mode="public"``.

Why share the collection? Same shape ⇒ same downstream services + a
single place for ``current_install`` to look. The ``mode`` discriminator
is the only branching point.

``GET /workspaces/search`` backs the picker's type-ahead. It is deliberately
cache-heavy: public search runs on a shared budget (10 req/min anonymously,
30 with a PAT), so every keystroke must NOT become a GitHub call. Results are
memoised by query, and account profiles — which change rarely — are memoised
per login so a repeat search costs nothing.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth.deps import current_user
from app.clients.github import gh_public
from app.core.db import get_db
from app.core.errors import GitHubError
from app.services import cache

router = APIRouter(prefix="/workspaces", tags=["workspaces"])

_SEARCH_TTL = 300  # a query's result set
_PROFILE_TTL = 3600  # /users/{login} — repo counts drift slowly


class AddPublicWorkspaceRequest(BaseModel):
    login: str = Field(..., min_length=1, max_length=64)


# ──────────────────────────────────────────────────────────────────────
# Search — type-ahead over GitHub accounts
# ──────────────────────────────────────────────────────────────────────
async def _profile(login: str) -> dict[str, Any] | None:
    """Cached ``/users/{login}`` lookup — gives repo count + description,
    which the search API itself does not return."""
    key = f"ghprofile:{login.lower()}"
    if (hit := cache.get(key)) is not None:
        return hit or None
    try:
        data = await gh_public().get(f"/users/{login}")
    except Exception:
        cache.set_(key, {}, 60)  # brief negative cache; don't retry per keystroke
        return None
    slim = {
        "login": data["login"],
        "name": data.get("name"),
        "avatar_url": data.get("avatar_url"),
        "type": data.get("type", "User"),
        "description": (data.get("bio") or data.get("description") or "").strip(),
        "public_repos": data.get("public_repos", 0),
        "followers": data.get("followers", 0),
        "html_url": data.get("html_url"),
    }
    cache.set_(key, slim, _PROFILE_TTL)
    return slim


async def _already_added(user_id: int) -> set[str]:
    """Logins this user already has a workspace for — so the UI can show
    "Added" instead of offering a duplicate."""
    db = get_db()
    cursor = db["installations"].find(
        {"$or": [{"mode": "public", "owner_user_id": user_id}, {"mode": {"$ne": "public"}}]},
        {"account_login": 1},
    )
    return {doc["account_login"].lower() async for doc in cursor if doc.get("account_login")}


@router.get("/search")
async def search_accounts(
    q: str = Query(..., min_length=1, max_length=64),
    limit: int = Query(6, ge=1, le=10),
    user: dict = Depends(current_user),
) -> dict:
    """Type-ahead over GitHub orgs and users.

    Organizations rank first (they're what a workspace is usually for); if the
    org search is thin we top up with user accounts. Each hit is hydrated with
    its repo count and description so the picker can show something meaningful
    rather than a bare login.
    """
    query = q.strip()
    if not query:
        return {"query": q, "results": [], "rate_limited": False}

    cache_key = f"wssearch:{query.lower()}:{limit}"
    cached = cache.get(cache_key)
    if cached is None:
        gh = gh_public()
        logins: list[str] = []
        rate_limited = False

        async def _search(expr: str) -> list[str]:
            data = await gh.get(
                "/search/users", params={"q": expr, "per_page": limit}
            )
            return [it["login"] for it in (data.get("items") or [])]

        try:
            logins = await _search(f"{query} type:org")
            # Thin org results (a personal account like "sindresorhus", or a
            # narrow term) → top up with users rather than showing nothing.
            if len(logins) < 3:
                seen = {ln.lower() for ln in logins}
                for extra in await _search(f"{query} type:user"):
                    if extra.lower() not in seen:
                        logins.append(extra)
        except GitHubError as exc:
            # 403/429 here means the shared search budget is spent. Say so
            # explicitly so the UI can explain it instead of showing "error".
            rate_limited = exc.status in (403, 429)
            if not rate_limited:
                raise

        profiles = await asyncio.gather(
            *(_profile(ln) for ln in logins[: limit * 2]), return_exceptions=True
        )
        results = [p for p in profiles if isinstance(p, dict)]
        # Orgs first, then by repo count — the useful signal for "can I get a
        # real dashboard out of this account?"
        results.sort(
            key=lambda r: (r["type"] != "Organization", -(r.get("public_repos") or 0))
        )
        cached = {"results": results[:limit], "rate_limited": rate_limited}
        if not rate_limited:
            cache.set_(cache_key, cached, _SEARCH_TTL)

    added = await _already_added(user["github_id"])
    return {
        "query": query,
        "rate_limited": cached["rate_limited"],
        "results": [
            {**r, "already_added": r["login"].lower() in added} for r in cached["results"]
        ],
    }


@router.post("/public")
async def add_public_workspace(
    body: AddPublicWorkspaceRequest,
    user: dict = Depends(current_user),
) -> dict:
    """Verify the org/user exists publicly, then save a public workspace
    row owned by the current user."""
    login = body.login.strip()
    if not login.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail="invalid_login")

    # Probe GitHub. /users/{login} returns user-or-org with a `type` field.
    try:
        profile = await gh_public().get(f"/users/{login}")
    except GitHubError as exc:
        if exc.status == 404:
            raise HTTPException(status_code=404, detail="github_account_not_found") from exc
        raise

    account_type = profile.get("type", "User")  # "User" or "Organization"
    canonical_login = profile["login"]
    db = get_db()

    doc = {
        "account_login": canonical_login.lower(),
        "account_login_display": canonical_login,
        "account_type": account_type,
        "account_id": profile["id"],
        "avatar_url": profile.get("avatar_url"),
        "mode": "public",
        "owner_user_id": user["github_id"],
        "repository_selection": "all",
        "permissions": {},
        "events": [],
        "updated_at": datetime.now(timezone.utc),
    }
    await db["installations"].update_one(
        {
            "mode": "public",
            "owner_user_id": user["github_id"],
            "account_login": canonical_login.lower(),
        },
        {"$set": doc, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    inserted = await db["installations"].find_one(
        {
            "mode": "public",
            "owner_user_id": user["github_id"],
            "account_login": canonical_login.lower(),
        }
    )
    if inserted is None:  # pragma: no cover - upsert race
        raise HTTPException(status_code=500, detail="workspace_save_failed")
    return _serialize(inserted)


@router.delete("/public/{login}")
async def remove_public_workspace(
    login: str,
    user: dict = Depends(current_user),
) -> dict:
    db = get_db()
    res = await db["installations"].delete_one(
        {
            "mode": "public",
            "owner_user_id": user["github_id"],
            "account_login": login.lower(),
        }
    )
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="workspace_not_found")
    # Deliberately NOT purging this account's RAG index (unlike an App
    # uninstall): public tenants are shared by every user tracking the same
    # account, so one user removing their workspace must not delete an index
    # another user is still querying. It only holds public data, and it stops
    # being refreshed once no workspace references it.
    return {"removed": login}


def _serialize(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "account_login": doc.get("account_login_display") or doc.get("account_login"),
        "account_type": doc.get("account_type"),
        "mode": doc.get("mode", "install"),
        "avatar_url": doc.get("avatar_url"),
        "install_id": doc.get("install_id"),
    }
