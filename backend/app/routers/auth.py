"""Auth router — login, callback, logout, me, install, org listing."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from app.auth import oauth
from app.auth.deps import current_user
from app.auth.session import clear_session, write_session
from app.core.config import get_settings
from app.core.db import get_db

router = APIRouter(prefix="/auth", tags=["auth"])

# State cookie holds the OAuth state value for CSRF protection between
# /auth/login and /auth/callback.
_STATE_COOKIE = "dypol_oauth_state"


@router.get("/login")
async def login() -> RedirectResponse:
    state = oauth.new_state()
    response = RedirectResponse(url=oauth.authorize_url(state))
    response.set_cookie(
        _STATE_COOKIE,
        state,
        max_age=600,
        httponly=True,
        secure=get_settings().is_prod,
        samesite="lax",
        path="/auth",
    )
    return response


@router.get("/callback")
async def callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
) -> RedirectResponse:
    expected = request.cookies.get(_STATE_COOKIE)
    if not expected or expected != state:
        raise HTTPException(status_code=400, detail="bad_oauth_state")

    user_token = await oauth.exchange_code(code)
    profile = await oauth.fetch_user(user_token)
    orgs = await oauth.fetch_user_orgs(user_token)
    emails = await oauth.fetch_user_emails(user_token)

    # Store full org objects so we can build install URLs later.
    org_records = [
        {
            "id": o["id"],
            "login": o["login"],
            "avatar_url": o.get("avatar_url"),
            "description": o.get("description"),
        }
        for o in orgs
    ]

    user_doc = {
        "github_id": profile["id"],
        "login": profile["login"],
        "name": profile.get("name"),
        "email": oauth.primary_email(emails) or profile.get("email"),
        "avatar_url": profile.get("avatar_url"),
        "orgs": [o["login"] for o in orgs],          # legacy field, keep for now
        "orgs_full": org_records,                     # new — used by /auth/orgs
        "last_login": datetime.now(timezone.utc),
    }
    await get_db()["users"].update_one(
        {"github_id": profile["id"]},
        {"$set": user_doc, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )

    response = RedirectResponse(url=f"{get_settings().web_base_url}/dashboard")
    response.delete_cookie(_STATE_COOKIE, path="/auth")
    write_session(response, {"user_id": profile["id"], "login": profile["login"]})
    return response


@router.post("/logout")
async def logout() -> dict:
    response = RedirectResponse(url=get_settings().web_base_url, status_code=303)
    clear_session(response)
    return response  # type: ignore[return-value]


@router.get("/me")
async def me(user: dict = Depends(current_user)) -> dict:
    """Return user profile + every workspace they can use.

    A workspace is either:
      - an App installation on an account they belong to, OR
      - a public-org workspace they explicitly added (read-only).
    """
    db = get_db()
    user_orgs_lower = [o.lower() for o in (user.get("orgs") or [])]
    user_orgs_lower.append(user["login"].lower())

    cursor = db["installations"].find(
        {
            "$or": [
                {
                    "account_login": {"$in": user_orgs_lower},
                    "mode": {"$ne": "public"},
                },
                {"mode": "public", "owner_user_id": user["github_id"]},
            ]
        }
    )
    installations: list[dict] = []
    async for doc in cursor:
        installations.append(
            {
                "install_id": doc.get("install_id"),
                "account_login": doc.get("account_login_display")
                or doc["account_login"],
                "account_type": doc.get("account_type"),
                "repository_selection": doc.get("repository_selection"),
                "mode": doc.get("mode", "install"),
                "avatar_url": doc.get("avatar_url"),
            }
        )
    return {
        "user": {
            "login": user["login"],
            "name": user.get("name"),
            "email": user.get("email"),
            "avatar_url": user.get("avatar_url"),
        },
        "installations": installations,
    }


@router.get("/orgs")
async def list_user_connections(user: dict = Depends(current_user)) -> dict:
    """List the user's existing workspaces + a generic 'connect new' URL.

    Includes both App installs (full access) and public-org workspaces
    (read-only, no install needed).
    """
    s = get_settings()
    db = get_db()

    candidate_logins = {user["login"].lower()}
    for o in user.get("orgs") or []:
        candidate_logins.add(o.lower())

    cursor = db["installations"].find(
        {
            "$or": [
                {
                    "account_login": {"$in": list(candidate_logins)},
                    "mode": {"$ne": "public"},
                },
                {"mode": "public", "owner_user_id": user["github_id"]},
            ]
        }
    )
    connected = [
        {
            "type": "User" if doc.get("account_type") == "User" else "Organization",
            "login": doc.get("account_login_display") or doc["account_login"],
            "id": doc.get("account_id"),
            "avatar_url": doc.get("avatar_url"),
            "installed": True,
            "install_id": doc.get("install_id"),
            "mode": doc.get("mode", "install"),
            "repository_selection": doc.get("repository_selection"),
            "repositories_count": len(doc.get("repositories") or []),
        }
        async for doc in cursor
    ]

    # One install URL — GitHub's /select_target route always shows the
    # account picker (unlike /installations/new which redirects to the
    # last-used target if you're already logged in). User sees every
    # account they're a member of, public + private.
    install_url = (
        f"https://github.com/apps/{s.github_app_slug}/installations/select_target"
    )

    return {
        "connected": connected,
        "install_url": install_url,
    }


@router.get("/install")
async def install_redirect(
    target_id: int | None = Query(default=None),
    target_type: str | None = Query(default=None),
) -> RedirectResponse:
    """Redirect to the App install page.

    If ``target_id`` is provided, the URL is pre-targeted at that account so
    GitHub skips the account picker. Pass ``target_type=Organization`` for
    org installs.
    """
    s = get_settings()
    base = f"https://github.com/apps/{s.github_app_slug}/installations/new/permissions"
    if target_id:
        url = f"{base}?target_id={target_id}"
        if target_type:
            url += f"&target_type={target_type}"
    else:
        url = s.install_url
    return RedirectResponse(url=url)
