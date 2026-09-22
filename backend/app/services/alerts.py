from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.clients.github import gh_for
from app.core.errors import GitHubError
from app.models.schemas import Alert
from app.services import cache
from app.services.prs import list_org_prs

log = logging.getLogger("dypol.alerts")

# The four alert sources are independent upstreams; a cold sweep of all four
# used to run strictly sequentially (~8 GitHub round-trips). Cache the
# assembled list for a minute so tab-switching and the dashboard's alert
# panel don't re-walk the world on every load.
_ALERTS_CACHE_TTL = 60


async def list_alerts(install_id: int | None, org_login: str, limit: int = 100) -> list[Alert]:
    key = f"alerts:{install_id or 'public:' + org_login.lower()}:{limit}"
    if (cached := cache.get(key)) is not None:
        return cached

    # Independent sources — run them concurrently instead of one-by-one.
    # return_exceptions keeps one rate-limited source from losing the others.
    stuck, failing, dependabot, scanning = await asyncio.gather(
        _stuck_prs(install_id, org_login),
        _failing_check_runs(install_id, org_login),
        _dependabot_alerts(install_id, org_login),
        _code_scanning_alerts(install_id, org_login),
        return_exceptions=True,
    )

    out: list[Alert] = []
    for result, label in (
        (stuck, "stuck_prs"),
        (failing, "failing_check_runs"),
        (dependabot, "dependabot_alerts"),
        (scanning, "code_scanning_alerts"),
    ):
        if isinstance(result, BaseException):
            # Sources already swallow GitHubError internally; anything that
            # escapes is unexpected — log it and degrade to an empty source
            # rather than failing the whole alerts view.
            log.warning("alerts source %s failed: %s", label, result)
            continue
        out.extend(result)

    out.sort(
        key=lambda a: (
            {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(a.severity, 99),
            -(a.created_at.timestamp() if a.created_at else 0),
        )
    )
    out = out[:limit]
    cache.set_(key, out, _ALERTS_CACHE_TTL)
    return out


async def _stuck_prs(install_id: int | None, org_login: str) -> list[Alert]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    prs = await list_org_prs(install_id, org_login, state="open", limit=100)
    return [
        Alert(
            kind="stuck_pr",
            repo=p.repo,
            ref=f"#{p.number}",
            title=f"PR untouched 7+ days: {p.title}",
            severity="medium",
            url=p.html_url,
            created_at=p.updated_at,
        )
        for p in prs
        if not p.draft and p.updated_at < cutoff
    ]


async def _failing_check_runs(install_id: int | None, org_login: str) -> list[Alert]:
    q = f"org:{org_login} is:pr is:open status:failure"
    try:
        data = await gh_for(install_id).get("/search/issues", params={"q": q, "per_page": 50})
    except GitHubError:
        return []
    out: list[Alert] = []
    for it in data.get("items", []):
        repo_url: str = it.get("repository_url", "")
        repo_name = repo_url.rsplit("/", 1)[-1]
        out.append(
            Alert(
                kind="failing_check",
                repo=repo_name,
                ref=f"#{it['number']}",
                title=f"Failing checks: {it['title']}",
                severity="high",
                url=it["html_url"],
                created_at=datetime.fromisoformat(it["updated_at"].replace("Z", "+00:00")),
            )
        )
    return out


async def _dependabot_alerts(install_id: int | None, org_login: str) -> list[Alert]:
    try:
        items: list[dict[str, Any]] = await gh_for(install_id).collect(
            f"/orgs/{org_login}/dependabot/alerts",
            params={"state": "open"},
            max_pages=2,
        )
    except GitHubError:
        return []
    out: list[Alert] = []
    for it in items:
        adv = it.get("security_advisory") or {}
        repo = (it.get("repository") or {}).get("name", "")
        out.append(
            Alert(
                kind="dependabot",
                repo=repo,
                ref=f"alert-{it.get('number')}",
                title=adv.get("summary") or "Dependabot alert",
                severity=adv.get("severity", "medium"),
                url=it.get("html_url", ""),
                created_at=datetime.fromisoformat(it["created_at"].replace("Z", "+00:00")),
            )
        )
    return out


async def _code_scanning_alerts(install_id: int | None, org_login: str) -> list[Alert]:
    try:
        items: list[dict[str, Any]] = await gh_for(install_id).collect(
            f"/orgs/{org_login}/code-scanning/alerts",
            params={"state": "open"},
            max_pages=2,
        )
    except GitHubError:
        return []
    out: list[Alert] = []
    for it in items:
        rule = it.get("rule") or {}
        repo = (it.get("repository") or {}).get("name", "")
        out.append(
            Alert(
                kind="code_scanning",
                repo=repo,
                ref=f"alert-{it.get('number')}",
                title=rule.get("description") or rule.get("name") or "Code scanning alert",
                severity=rule.get("security_severity_level") or "medium",
                url=it.get("html_url", ""),
                created_at=datetime.fromisoformat(it["created_at"].replace("Z", "+00:00")),
            )
        )
    return out
