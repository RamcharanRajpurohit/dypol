"""FastAPI dependencies for auth.

``current_user``       — requires a valid session, returns user dict.
``current_install``    — resolves the active workspace (App install OR
                         public-org) from query/header to a workspace doc
                         the user is allowed to access.
"""
from __future__ import annotations

from typing import Any

from fastapi import Depends, Header, HTTPException, Query, status

from app.auth.session import read_session
from app.core.db import get_db
from fastapi import Request


async def current_user(request: Request) -> dict[str, Any]:
    sess = read_session(request)
    if not sess or "user_id" not in sess:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not_signed_in")
    user = await get_db()["users"].find_one({"github_id": sess["user_id"]})
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user_not_found")
    return user


def _can_access(user: dict[str, Any], workspace: dict[str, Any]) -> bool:
    """Authorization check — does this user own / belong to this workspace?

    - Install workspaces: user must be a member of the org (or it's their
      personal account).
    - Public workspaces: only the user who added it (one row per user).
    """
    login = (workspace.get("account_login") or "").lower()
    user_login = (user.get("login") or "").lower()
    user_orgs = {o.lower() for o in (user.get("orgs") or [])}

    if workspace.get("mode") == "public":
        return workspace.get("owner_user_id") == user["github_id"]

    return login == user_login or login in user_orgs


async def _resolve_workspace(user: dict[str, Any], org: str) -> dict[str, Any]:
    db = get_db()
    org_lower = org.lower()
    # Prefer a public workspace owned by this user (since multiple users
    # may track the same public org independently); fall back to a shared
    # install workspace.
    workspace = await db["installations"].find_one(
        {
            "account_login": org_lower,
            "mode": "public",
            "owner_user_id": user["github_id"],
        }
    )
    if not workspace:
        workspace = await db["installations"].find_one(
            {"account_login": org_lower, "mode": {"$ne": "public"}}
        )
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="workspace_not_found",
        )
    if workspace.get("suspended_at"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="installation_suspended"
        )
    if not _can_access(user, workspace):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not_a_member")
    return workspace


async def current_install(
    user: dict[str, Any] = Depends(current_user),
    org_q: str | None = Query(default=None, alias="org"),
    org_h: str | None = Header(default=None, alias="X-Org"),
) -> dict[str, Any]:
    """Resolve the active workspace. The org login comes from ``?org=…``
    or the ``X-Org`` header. If only one workspace exists, auto-pick it.
    Returns either an install doc or a public-mode doc."""
    org = org_q or org_h
    if not org:
        db = get_db()
        candidates = (user.get("orgs") or []) + [user.get("login")]
        candidates_lower = [c.lower() for c in candidates if c]
        cursor = db["installations"].find(
            {
                "$or": [
                    {"account_login": {"$in": candidates_lower}, "mode": {"$ne": "public"}},
                    {"mode": "public", "owner_user_id": user["github_id"]},
                ]
            }
        )
        workspaces = [doc async for doc in cursor]
        if len(workspaces) == 1:
            return workspaces[0]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="org_required" if workspaces else "no_installations",
        )
    return await _resolve_workspace(user, org)
