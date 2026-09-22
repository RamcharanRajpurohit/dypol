from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from app.clients.github import gh_for
from app.models.schemas import LeaderboardEntry
from app.services import cache
from app.services.repos import list_org_repos, repo_scan_cap

log = logging.getLogger("dypol.leaderboard")

# The leaderboard used to walk up to 30 repos × 2 commit pages strictly
# sequentially — 60 GitHub round-trips before any byte of response. Cache
# the computed board so repeat visits (and the digest, which calls into
# this) skip the walk entirely within the TTL.
_LEADERBOARD_CACHE_TTL = 120


async def compute_leaderboard(
    install_id: int | None, org_login: str, days: int = 30, limit: int = 25
) -> list[LeaderboardEntry]:
    cache_key = f"leaderboard:{install_id or 'public:' + org_login.lower()}:{days}:{limit}"
    if (cached := cache.get(cache_key)) is not None:
        return cached

    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    stats: dict[str, dict[str, float]] = defaultdict(
        lambda: {"commits": 0, "additions": 0, "deletions": 0, "prs_merged": 0, "reviews": 0}
    )
    avatars: dict[str, str] = {}
    names: dict[str, str | None] = {}

    repos = await list_org_repos(install_id, org_login)
    gh = gh_for(install_id)
    commit_pages = 2 if install_id is not None else 1
    scan = repos[: repo_scan_cap(install_id, install_cap=30)]

    # Fire the per-repo commit walks concurrently (bounded — 8 at a time keeps
    # total latency ≈ slowest repo × ⌈30/8⌉ instead of the sum of all 30).
    sem = asyncio.Semaphore(8)

    async def bounded(repo_full_name: str) -> list[dict]:
        async with sem:
            try:
                return await gh.collect(
                    f"/repos/{repo_full_name}/commits",
                    params={"since": since},
                    max_pages=commit_pages,
                )
            except Exception:
                # One dead/rate-limited repo shouldn't sink the board.
                return []

    per_repo = await asyncio.gather(*(bounded(r.full_name) for r in scan))
    for commits in per_repo:
        for c in commits:
            login = (c.get("author") or {}).get("login")
            if not login:
                continue
            stats[login]["commits"] += 1
            avatars[login] = (c.get("author") or {}).get("avatar_url", "")
            names.setdefault(login, (c.get("commit") or {}).get("author", {}).get("name"))

    pr_q = f"org:{org_login} is:pr is:merged merged:>={since[:10]}"
    try:
        pr_data = await gh.get("/search/issues", params={"q": pr_q, "per_page": 100})
    except Exception as exc:
        # Search is the first thing to 403 under a tight budget (10 req/min
        # anonymously). Degrade to a commits-only leaderboard rather than
        # failing the whole endpoint — every sibling call already does this.
        log.info("leaderboard PR search failed for %s: %s", org_login, exc)
        pr_data = {}
    for it in pr_data.get("items", []):
        login = (it.get("user") or {}).get("login")
        if login:
            stats[login]["prs_merged"] += 1

    entries: list[LeaderboardEntry] = []
    for login, st in stats.items():
        score = st["commits"] * 1.0 + st["prs_merged"] * 3.0 + st["reviews"] * 1.5
        entries.append(
            LeaderboardEntry(
                login=login,
                name=names.get(login),
                avatar_url=avatars.get(login, ""),
                commits=int(st["commits"]),
                additions=int(st["additions"]),
                deletions=int(st["deletions"]),
                prs_merged=int(st["prs_merged"]),
                reviews=int(st["reviews"]),
                score=round(score, 1),
                rank=0,
                delta=0.0,
            )
        )
    entries.sort(key=lambda e: e.score, reverse=True)
    for i, e in enumerate(entries[:limit], start=1):
        e.rank = i
    result = entries[:limit]

    cache.set_(cache_key, result, _LEADERBOARD_CACHE_TTL)
    return result
