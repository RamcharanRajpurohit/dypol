"""GitHub OAuth (user identity) flow.

Used only to identify *who is using the dashboard* — not to read org data.
Org data goes through installation tokens (see ``clients/github.py``).

Flow:
  1.  ``/auth/login``    — redirect user to GitHub authorize URL.
  2.  GitHub redirects back to ``/auth/callback?code=...`` after consent.
  3.  We exchange the code for a user access token, fetch /user, then drop
      the user token (we don't store it). A signed session cookie is set.
"""
from __future__ import annotations

import secrets
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.errors import GitHubError

# Scopes for *user identity* only.
# read:user → name, login, avatar
# user:email → primary email
# read:org → list orgs the user belongs to (so we can match to installations)
USER_SCOPES = "read:user user:email read:org"


def authorize_url(state: str) -> str:
    s = get_settings()
    params = {
        "client_id": s.github_app_client_id,
        "redirect_uri": s.oauth_redirect_uri,
        "scope": USER_SCOPES,
        "state": state,
        "allow_signup": "false",
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return f"https://github.com/login/oauth/authorize?{qs}"


def new_state() -> str:
    return secrets.token_urlsafe(32)


async def exchange_code(code: str) -> str:
    """Exchange OAuth code for a user access token. Token is short-lived and
    not persisted — we only use it to fetch the user's profile/orgs once."""
    s = get_settings()
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": s.github_app_client_id,
                "client_secret": s.github_app_client_secret,
                "code": code,
                "redirect_uri": s.oauth_redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
    if resp.status_code >= 400:
        raise GitHubError(resp.status_code, resp.text, str(resp.request.url))
    data = resp.json()
    if "error" in data:
        raise GitHubError(400, data.get("error_description", data["error"]))
    return data["access_token"]


async def fetch_user(token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
        )
    if resp.status_code >= 400:
        raise GitHubError(resp.status_code, resp.text)
    return resp.json()


async def fetch_user_orgs(token: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://api.github.com/user/orgs",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
        )
    if resp.status_code >= 400:
        raise GitHubError(resp.status_code, resp.text)
    return resp.json()


async def fetch_user_emails(token: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://api.github.com/user/emails",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
        )
    if resp.status_code >= 400:
        return []
    return resp.json()


def primary_email(emails: list[dict[str, Any]]) -> str | None:
    for e in emails:
        if e.get("primary") and e.get("verified"):
            return e.get("email")
    for e in emails:
        if e.get("verified"):
            return e.get("email")
    return None
