"""GitHub App client.

Two layers:

1.  App JWT  — short-lived (10 min) RS256 token signed with the App's private
    key. Identifies *the App itself* to GitHub. Used to look up installations
    and mint installation access tokens.

2.  Installation token — short-lived (~1 hour) token tied to a single
    installation (one org's install of our App). Used for all reads against
    that org's repos. Cached in Mongo with TTL until a few minutes before
    expiry, then refreshed automatically.

Per-request callers go through ``gh_for(install_id)`` which returns a thin
``GitHubClient`` bound to that org's installation.
"""
from __future__ import annotations

import time
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import jwt
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import GitHubError

# ──────────────────────────────────────────────────────────────────────
# App JWT — identifies our App to GitHub.
# Cached in-process; regenerated when within 60s of expiry.
# ──────────────────────────────────────────────────────────────────────
_app_jwt: tuple[str, float] | None = None  # (token, exp_epoch)


def _build_app_jwt() -> str:
    """Sign a 10-minute JWT with the App private key (RS256)."""
    s = get_settings()
    now = int(time.time())
    payload = {
        # iat slightly in the past to absorb clock skew
        "iat": now - 30,
        "exp": now + 9 * 60,  # 9 min — GitHub allows max 10
        "iss": s.github_app_id,
    }
    return jwt.encode(payload, s.load_private_key(), algorithm="RS256")


def get_app_jwt() -> str:
    global _app_jwt
    now = time.time()
    if _app_jwt is None or _app_jwt[1] - 60 < now:
        token = _build_app_jwt()
        _app_jwt = (token, now + 9 * 60)
    return _app_jwt[0]


# ──────────────────────────────────────────────────────────────────────
# Module-level shared httpx client.
# One pool, reused across all installations.
# ──────────────────────────────────────────────────────────────────────
_pool: httpx.AsyncClient | None = None


def _get_pool() -> httpx.AsyncClient:
    global _pool
    if _pool is None:
        _pool = httpx.AsyncClient(
            base_url=get_settings().github_api_base,
            timeout=httpx.Timeout(20.0, connect=5.0),
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "dypol-backend/0.1",
            },
        )
    return _pool


async def close() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None


# ──────────────────────────────────────────────────────────────────────
# Installation access tokens — Mongo-cached.
# Collection: install_tokens  { install_id, token, expires_at }
# TTL index on expires_at auto-purges expired tokens.
# ──────────────────────────────────────────────────────────────────────
async def _fetch_installation_token(install_id: int) -> tuple[str, datetime]:
    """Mint a fresh installation token via the App JWT."""
    resp = await _get_pool().post(
        f"/app/installations/{install_id}/access_tokens",
        headers={"Authorization": f"Bearer {get_app_jwt()}"},
    )
    if resp.status_code >= 400:
        raise GitHubError(resp.status_code, resp.text, str(resp.request.url))
    data = resp.json()
    expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
    return data["token"], expires_at


async def get_installation_token(install_id: int) -> str:
    """Return a non-expired installation token, fetching/refreshing as needed."""
    db = get_db()
    now = datetime.now(timezone.utc)
    cached = await db["install_tokens"].find_one({"install_id": install_id})
    if cached and cached["expires_at"] - timedelta(minutes=5) > now:
        return cached["token"]

    token, expires_at = await _fetch_installation_token(install_id)
    await db["install_tokens"].update_one(
        {"install_id": install_id},
        {"$set": {"token": token, "expires_at": expires_at, "install_id": install_id}},
        upsert=True,
    )
    return token


# ──────────────────────────────────────────────────────────────────────
# GitHubClient — per-installation wrapper. Stateless, cheap to construct.
# ──────────────────────────────────────────────────────────────────────
class GitHubClient:
    """Async GitHub REST client bound to a specific installation."""

    def __init__(self, install_id: int) -> None:
        self.install_id = install_id

    async def _auth_header(self) -> dict[str, str]:
        token = await get_installation_token(self.install_id)
        return {"Authorization": f"Bearer {token}"}

    async def _request(self, method: str, path: str, **kw: Any) -> httpx.Response:
        client = _get_pool()
        headers = {**(kw.pop("headers", {}) or {}), **(await self._auth_header())}
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
            retry=retry_if_exception_type((httpx.TransportError, httpx.ReadTimeout)),
            reraise=True,
        ):
            with attempt:
                resp = await client.request(method, path, headers=headers, **kw)
        if resp.status_code == 404:
            raise GitHubError(404, "not found", str(resp.request.url))
        if resp.status_code >= 400:
            try:
                msg = resp.json().get("message", resp.text)
            except Exception:
                msg = resp.text
            raise GitHubError(resp.status_code, msg, str(resp.request.url))
        return resp

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        resp = await self._request("GET", path, params=params)
        return resp.json()

    async def paginate(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        max_pages: int = 10,
        per_page: int = 100,
    ) -> AsyncIterator[Any]:
        params = {**(params or {}), "per_page": per_page, "page": 1}
        for _ in range(max_pages):
            resp = await self._request("GET", path, params=params)
            data = resp.json()
            if not isinstance(data, list):
                yield data
                return
            if not data:
                return
            for item in data:
                yield item
            if "next" not in (resp.headers.get("Link") or ""):
                return
            params["page"] += 1

    async def collect(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        max_pages: int = 10,
        per_page: int = 100,
    ) -> list[Any]:
        return [item async for item in self.paginate(path, params, max_pages, per_page)]

    async def graphql(
        self, query: str, variables: dict[str, Any] | None = None
    ) -> Any:
        """Run a GitHub GraphQL v4 query (read-only). Used for blame and other
        data the REST API doesn't expose. Uses the installation token."""
        resp = await self._request(
            "POST", "/graphql", json={"query": query, "variables": variables or {}}
        )
        return resp.json()


def gh_for(install_id: int | None) -> "GitHubClient | PublicGitHubClient":
    """Factory: returns an installation-token client when ``install_id`` is
    given, otherwise the public (PAT or anonymous) client. Services call
    this with whatever the caller has — ``None`` means "public-mode
    workspace, no install token to use"."""
    if install_id is None:
        return gh_public()
    return GitHubClient(install_id)


class PublicGitHubClient:
    """Read-only client for **public** GitHub data — no installation required.

    Authenticates with a server-side PAT (``GITHUB_PAT``) when one is set,
    otherwise hits the API anonymously. Used for ``public`` workspaces
    where the App is *not* installed on the target org.

    Same surface as ``GitHubClient`` (``get`` / ``paginate`` / ``collect``)
    so services can call it interchangeably.
    """

    async def _auth_header(self) -> dict[str, str]:
        pat = get_settings().github_pat
        return {"Authorization": f"Bearer {pat}"} if pat else {}

    async def _request(self, method: str, path: str, **kw: Any) -> httpx.Response:
        client = _get_pool()
        headers = {**(kw.pop("headers", {}) or {}), **(await self._auth_header())}
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
            retry=retry_if_exception_type((httpx.TransportError, httpx.ReadTimeout)),
            reraise=True,
        ):
            with attempt:
                resp = await client.request(method, path, headers=headers, **kw)
        if resp.status_code == 404:
            raise GitHubError(404, "not found", str(resp.request.url))
        if resp.status_code >= 400:
            try:
                msg = resp.json().get("message", resp.text)
            except Exception:
                msg = resp.text
            raise GitHubError(resp.status_code, msg, str(resp.request.url))
        return resp

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        resp = await self._request("GET", path, params=params)
        return resp.json()

    async def paginate(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        max_pages: int = 10,
        per_page: int = 100,
    ) -> AsyncIterator[Any]:
        params = {**(params or {}), "per_page": per_page, "page": 1}
        for _ in range(max_pages):
            resp = await self._request("GET", path, params=params)
            data = resp.json()
            if not isinstance(data, list):
                yield data
                return
            if not data:
                return
            for item in data:
                yield item
            if "next" not in (resp.headers.get("Link") or ""):
                return
            params["page"] += 1

    async def collect(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        max_pages: int = 10,
        per_page: int = 100,
    ) -> list[Any]:
        return [item async for item in self.paginate(path, params, max_pages, per_page)]


_public_client: PublicGitHubClient | None = None


def gh_public() -> PublicGitHubClient:
    """Singleton public client. Use for read-only public-org workspaces."""
    global _public_client
    if _public_client is None:
        _public_client = PublicGitHubClient()
    return _public_client


def gh_for_workspace(workspace: dict[str, Any]) -> "GitHubClient | PublicGitHubClient":
    """Resolve the right client for a workspace doc.

    Workspace shapes:
      - GitHub App install:  has ``install_id``, ``mode == "install"`` (or absent)
      - Public read-only:    ``mode == "public"``, no ``install_id``
    """
    if workspace.get("mode") == "public":
        return gh_public()
    install_id = workspace.get("install_id")
    if install_id is None:
        raise ValueError("workspace has neither install_id nor mode=public")
    return gh_for(install_id)


# ──────────────────────────────────────────────────────────────────────
# App-level helpers (use the App JWT directly, not an install token).
# Used during the install/OAuth bootstrap.
# ──────────────────────────────────────────────────────────────────────
async def app_get(path: str, params: dict[str, Any] | None = None) -> Any:
    resp = await _get_pool().get(
        path,
        params=params,
        headers={"Authorization": f"Bearer {get_app_jwt()}"},
    )
    if resp.status_code >= 400:
        raise GitHubError(resp.status_code, resp.text, str(resp.request.url))
    return resp.json()


async def list_installations() -> list[dict[str, Any]]:
    """All installations of this App across orgs/users."""
    return await app_get("/app/installations", params={"per_page": 100})


async def get_installation_for_account(login: str) -> dict[str, Any] | None:
    """Find the install for a given org or user login, if any."""
    for inst in await list_installations():
        account = inst.get("account") or {}
        if account.get("login", "").lower() == login.lower():
            return inst
    return None
