from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.clients.github import gh_for
from app.core.config import get_settings
from app.models.schemas import Repo, Status
from app.services import cache

# Search pages swept for open-PR counts (100 PRs each). Three covers all but
# the very busiest accounts while keeping the list to a few requests.
_PR_COUNT_PAGES = 3


def _status_for(open_prs: int, pushed_at: datetime | None) -> Status:
    now = datetime.now(timezone.utc)
    stale_days = (now - pushed_at).days if pushed_at else 999
    if open_prs >= 10:
        return "hot"
    if stale_days > 14 and open_prs > 0:
        return "stuck"
    if open_prs > 0:
        return "ok"
    return "neutral"


def _to_repo(raw: dict[str, Any], open_prs: int = 0, open_prs_approx: bool = False) -> Repo:
    pushed = raw.get("pushed_at")
    pushed_dt = datetime.fromisoformat(pushed.replace("Z", "+00:00")) if pushed else None
    return Repo(
        name=raw["name"],
        full_name=raw["full_name"],
        private=raw.get("private", False),
        archived=raw.get("archived", False),
        default_branch=raw.get("default_branch", "main"),
        open_issues_count=raw.get("open_issues_count", 0),
        open_prs=open_prs,
        open_prs_approx=open_prs_approx,
        pushed_at=pushed_dt,
        status=_status_for(open_prs, pushed_dt),
        summary=raw.get("description") or "",
        spark=[],
        html_url=raw["html_url"],
    )


def repo_scan_cap(install_id: int | None, install_cap: int = 30) -> int:
    """How many repos a per-repo scan (commits, stats) may walk.

    Request budgets are wildly different between the two workspace modes:
    an installation token gets its own 5,000+ req/hr, while EVERY public
    workspace shares a single budget — 5,000/hr when ``GITHUB_PAT`` is set,
    and just **60/hr** anonymously. Walking 30 repos would spend an entire
    anonymous hour on one page load, so public mode scans a shallower slice.
    """
    if install_id is not None:
        return install_cap
    return min(install_cap, 20 if get_settings().github_pat else 5)


async def list_org_repos(
    install_id: int | None,
    org_login: str | None = None,
    include_archived: bool = False,
) -> list[Repo]:
    """List repos for the active workspace.

    - With ``install_id``: hits ``/installation/repositories`` (sees private
      repos the App can read).
    - Public mode (``install_id=None``): falls back to public listing via
      ``/orgs/{login}/repos`` or ``/users/{login}/repos`` and only returns
      what's publicly visible.
    """
    s = get_settings()
    cache_key = f"repos:{install_id or 'public:' + (org_login or '')}:{include_archived}"
    if cached := cache.get(cache_key):
        return cached

    gh = gh_for(install_id)
    if install_id is not None:
        raw = await gh.collect(
            "/installation/repositories",
            params={"per_page": 100},
            max_pages=10,
        )
        # /installation/repositories returns objects with 'repositories' wrapper
        # when called via App; collect() flattens lists, so we pull directly.
        if raw and isinstance(raw[0], dict) and "repositories" in raw[0]:
            flat: list[dict[str, Any]] = []
            for page in raw:
                flat.extend(page.get("repositories", []))
            raw = flat
    else:
        if not org_login:
            return []
        # Try org endpoint first; fall back to user endpoint for personal accounts.
        try:
            raw = await gh.collect(
                f"/orgs/{org_login}/repos",
                params={"per_page": 100, "type": "public"},
                max_pages=5,
            )
        except Exception:
            raw = await gh.collect(
                f"/users/{org_login}/repos",
                params={"per_page": 100, "type": "owner"},
                max_pages=5,
            )

    kept = [r for r in raw if include_archived or not r.get("archived")]
    # Open-PR counts for the WHOLE list in one search (see _open_pr_counts).
    # Without this every repo reported 0 open PRs and _status_for() collapsed
    # every row to "neutral".
    counts, partial = await _open_pr_counts(install_id, org_login, kept)
    repos = [
        _to_repo(
            r,
            open_prs=counts.get(r["name"], 0),
            # Only flag repos we actually saw — a repo with zero hits genuinely
            # has zero, whereas a counted repo may have more beyond the cap.
            open_prs_approx=partial and counts.get(r["name"], 0) > 0,
        )
        for r in kept
    ]
    cache.set_(cache_key, repos, s.cache_ttl_repos)
    return repos


async def _open_pr_counts(
    install_id: int | None,
    org_login: str | None,
    repos: list[dict[str, Any]],
) -> tuple[dict[str, int], bool]:
    """Open PR count per repo name. Returns ``(counts, partial)``.

    One org-wide ``/search/issues`` sweep instead of one ``/pulls`` request per
    repo: an account with 80 repos would otherwise cost 80 requests just to
    render the list — more than the entire anonymous hourly budget.

    ``partial`` is True when the account has more open PRs than the sweep
    covered (``total_count`` exceeds what we paged through). Counts are then
    LOWER BOUNDS, and callers must present them as such: astral-sh has ~600
    open PRs org-wide, so a 300-PR sweep would otherwise report ruff as 78
    when the real figure is 387.

    Returns ``({}, False)`` on any failure — the list still renders.
    """
    if not org_login or not repos:
        return {}, False

    owner = org_login.lower()
    counts: dict[str, int] = {}
    seen = 0
    total = 0
    gh = gh_for(install_id)
    for page in range(1, _PR_COUNT_PAGES + 1):
        try:
            data = await gh.get(
                "/search/issues",
                params={
                    "q": f"org:{org_login} is:pr is:open",
                    "per_page": 100,
                    "page": page,
                },
            )
        except Exception:
            # Budget spent or upstream hiccup — keep what we have, and treat it
            # as partial so nothing we did count is presented as exact.
            return counts, bool(counts)
        items = data.get("items") or []
        total = int(data.get("total_count") or 0)
        seen += len(items)
        for it in items:
            repo_url = it.get("repository_url") or ""
            full = repo_url.split("/repos/", 1)[-1]
            repo_owner, _, name = full.partition("/")
            # search can surface forks in other accounts — keep ours only
            if name and repo_owner.lower() == owner:
                counts[name] = counts.get(name, 0) + 1
        if len(items) < 100:
            break
    return counts, seen < total


async def get_repo(install_id: int | None, full_name: str) -> Repo:
    raw = await gh_for(install_id).get(f"/repos/{full_name}")
    open_prs = await _count_open_prs(install_id, full_name)
    return _to_repo(raw, open_prs=open_prs)


async def _count_open_prs(install_id: int | None, full_name: str) -> int:
    """Exact open-PR count for ONE repo.

    Search reports ``total_count`` for the whole result set, so a single
    request gives the true figure — the previous approach paged ``/pulls`` and
    capped at 200, silently under-reporting busy repos (ruff has ~390).
    Falls back to paging if search is unavailable or rate-limited.
    """
    gh = gh_for(install_id)
    try:
        data = await gh.get(
            "/search/issues",
            params={"q": f"repo:{full_name} is:pr is:open", "per_page": 1},
        )
        return int(data.get("total_count") or 0)
    except Exception:
        items = await gh.collect(
            f"/repos/{full_name}/pulls",
            params={"state": "open"},
            max_pages=2,
        )
        return len(items)


async def repo_commit_activity(install_id: int | None, full_name: str) -> list[int]:
    try:
        data = await gh_for(install_id).get(f"/repos/{full_name}/stats/participation")
    except Exception:
        return []
    return list(data.get("all", []))[-12:]
