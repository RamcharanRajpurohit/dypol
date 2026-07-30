from __future__ import annotations

from typing import Any

from app.clients.github import gh_for
from app.core.config import get_settings
from app.core.errors import GitHubError
from app.models.schemas import Member
from app.services import cache


def _to_member(raw: dict[str, Any], role: str | None = None) -> Member:
    return Member(
        login=raw["login"],
        name=raw.get("name"),
        avatar_url=raw["avatar_url"],
        role=role,
        html_url=raw["html_url"],
    )


async def list_members(install_id: int | None, org_login: str) -> list[Member]:
    s = get_settings()
    # Key on the org too: in public mode ``install_id`` is None for EVERY
    # workspace, so an install_id-only key served one org's members for all
    # of them (the cache is a process-global dict).
    key = f"members:{install_id or 'public'}:{org_login.lower()}"
    if cached := cache.get(key):
        return cached
    try:
        raw = await gh_for(install_id).collect(f"/orgs/{org_login}/members", max_pages=5)
    except GitHubError:
        # Personal-account installs don't have org members.
        raw = []
    members = [_to_member(m) for m in raw]
    cache.set_(key, members, s.cache_ttl_members)
    return members
