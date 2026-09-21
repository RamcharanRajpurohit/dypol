"""Live GitHub org-membership checks, cached.

``users.orgs`` is a snapshot taken once, at OAuth login. Orgs joined — or App
installs added — afterwards never appear in it, so every filter built on it
hides the new workspace from the user forever (the "new users only see the
default workspace" bug). These helpers verify membership against GitHub on
demand, cache the verdict in-process, and **heal the snapshot** by adding
confirmed orgs back to the user document, so later requests cost nothing.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from app.clients.github import GitHubClient, GitHubError
from app.core.db import get_db

log = logging.getLogger("dypol.membership")

_POSITIVE_TTL = 30 * 60  # member verdict — 30 min
_NEGATIVE_TTL = 10 * 60  # non-member verdict — 10 min

# (user_github_id, org_login) -> (is_member, expires_monotonic)
_cache: dict[tuple[int, str], tuple[bool, float]] = {}


def _cached(user_id: int, org: str) -> bool | None:
    hit = _cache.get((user_id, org))
    if hit is None:
        return None
    ok, expires = hit
    if expires < time.monotonic():
        _cache.pop((user_id, org), None)
        return None
    return ok


async def ensure_org_membership(
    user: dict[str, Any],
    org_login: str,
    workspace: dict[str, Any] | None = None,
) -> bool:
    """True if this user is a member of ``org_login``.

    Fast paths: already present in the user's orgs snapshot, or a cached
    verdict. Slow path: ``GET /orgs/{org}/members/{user}`` with the org's
    installation token (204 = member, 404 = not). Confirmed members are
    persisted into ``users.orgs`` so subsequent requests skip GitHub.

    GitHub-side failures (5xx / transport) fail **open** — they are not an
    authorization answer, and locking real members out during an incident is
    worse than a brief over-show. Such verdicts are never cached.
    """
    org = org_login.lower()
    user_login = (user.get("login") or "").lower()
    user_id = user.get("github_id")

    if org in {o.lower() for o in (user.get("orgs") or [])}:
        return True
    if user_id is not None and (hit := _cached(int(user_id), org)) is not None:
        return hit

    install_id = (workspace or {}).get("install_id")
    if install_id is None:
        # No installation token to ask with — cannot verify, don't guess.
        return False

    try:
        status = await GitHubClient(int(install_id)).status_code(
            f"/orgs/{org}/members/{user_login}"
        )
        member = status == 204
    except GitHubError as exc:
        if exc.status >= 500:
            log.warning(
                "membership check %s/%s errored (failing open): %s",
                org,
                user_login,
                exc,
            )
            return True
        member = False  # 404 (or other 4xx) — a real "no access" answer
    except Exception as exc:
        log.warning(
            "membership check %s/%s failed (failing open): %s",
            org,
            user_login,
            exc,
        )
        return True

    if user_id is not None:
        ttl = _POSITIVE_TTL if member else _NEGATIVE_TTL
        _cache[(int(user_id), org)] = (member, time.monotonic() + ttl)

    if member:
        # Heal the login-time snapshot so later requests need no GitHub call.
        await get_db()["users"].update_one(
            {"github_id": user_id}, {"$addToSet": {"orgs": org}}
        )
        user.setdefault("orgs", []).append(org)
    return member
