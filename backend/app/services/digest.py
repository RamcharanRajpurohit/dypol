from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.clients.github import gh_for
from app.models.schemas import Contributor, DigestSummary, Repo
from app.services import cache
from app.services.leaderboard import compute_leaderboard
from app.services.repos import list_org_repos

log = logging.getLogger("dypol.digest")

# Cold build fans out to Search ×2 + leaderboard (up to ~60 upstream calls)
# + repo list. Cache the assembled digest so repeat views are instant and
# the upstream fan-out happens at most once every two minutes.
_DIGEST_CACHE_TTL = 120


async def _search_total(gh: Any, q: str) -> dict[str, Any]:
    """Search-API count that degrades to zero instead of failing the digest —
    public workspaces share a 10 req/min search budget and 403 easily."""
    try:
        return await gh.get("/search/issues", params={"q": q, "per_page": 1})
    except Exception as exc:
        log.info("digest search failed (%s): %s", q, exc)
        return {}


async def weekly_digest(install_id: int | None, org_login: str, days: int = 7) -> DigestSummary:
    cache_key = f"digest:{install_id or 'public:' + org_login.lower()}:{days}"
    if (cached := cache.get(cache_key)) is not None:
        return cached

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    since = start.date().isoformat()

    gh = gh_for(install_id)
    opened_q = f"org:{org_login} is:pr created:>={since}"
    merged_q = f"org:{org_login} is:pr is:merged merged:>={since}"

    # All four inputs are independent of each other (leaderboard fetches the
    # repo list itself) — run them concurrently instead of back-to-back.
    opened, merged, leaders, repos_results = await asyncio.gather(
        _search_total(gh, opened_q),
        _search_total(gh, merged_q),
        compute_leaderboard(install_id, org_login, days=days, limit=5),
        list_org_repos(install_id, org_login),
        return_exceptions=True,
    )
    # Each piece degrades to its "empty" shape rather than failing the view.
    opened = {} if isinstance(opened, BaseException) else opened
    merged = {} if isinstance(merged, BaseException) else merged
    leaders = [] if isinstance(leaders, BaseException) else leaders
    repos = [] if isinstance(repos_results, BaseException) else repos_results

    top_contribs = [
        Contributor(**leader.model_dump(exclude={"rank", "delta"})) for leader in leaders
    ]

    top_repos: list[Repo] = sorted(
        repos, key=lambda r: r.pushed_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True
    )[:5]

    commits_count = sum(c.commits for c in top_contribs)

    digest = DigestSummary(
        period_start=start,
        period_end=end,
        prs_opened=int(opened.get("total_count", 0)),
        prs_merged=int(merged.get("total_count", 0)),
        commits=commits_count,
        reviews=0,
        top_contributors=top_contribs,
        top_repos=top_repos,
    )
    cache.set_(cache_key, digest, _DIGEST_CACHE_TTL)
    return digest
