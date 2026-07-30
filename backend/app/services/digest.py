from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.clients.github import gh_for
from app.models.schemas import Contributor, DigestSummary, Repo
from app.services.leaderboard import compute_leaderboard
from app.services.repos import list_org_repos

log = logging.getLogger("dypol.digest")


async def _search_total(gh: Any, q: str) -> dict[str, Any]:
    """Search-API count that degrades to zero instead of failing the digest —
    public workspaces share a 10 req/min search budget and 403 easily."""
    try:
        return await gh.get("/search/issues", params={"q": q, "per_page": 1})
    except Exception as exc:
        log.info("digest search failed (%s): %s", q, exc)
        return {}


async def weekly_digest(install_id: int | None, org_login: str, days: int = 7) -> DigestSummary:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    since = start.date().isoformat()

    gh = gh_for(install_id)
    opened_q = f"org:{org_login} is:pr created:>={since}"
    merged_q = f"org:{org_login} is:pr is:merged merged:>={since}"
    opened = await _search_total(gh, opened_q)
    merged = await _search_total(gh, merged_q)

    leaders = await compute_leaderboard(install_id, org_login, days=days, limit=5)
    top_contribs = [
        Contributor(**leader.model_dump(exclude={"rank", "delta"})) for leader in leaders
    ]

    repos = await list_org_repos(install_id, org_login)
    top_repos: list[Repo] = sorted(
        repos, key=lambda r: r.pushed_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True
    )[:5]

    commits_count = sum(c.commits for c in top_contribs)

    return DigestSummary(
        period_start=start,
        period_end=end,
        prs_opened=int(opened.get("total_count", 0)),
        prs_merged=int(merged.get("total_count", 0)),
        commits=commits_count,
        reviews=0,
        top_contributors=top_contribs,
        top_repos=top_repos,
    )
