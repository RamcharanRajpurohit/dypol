from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.clients.github import gh_for
from app.core.errors import GitHubError
from app.models.schemas import Alert
from app.services.prs import list_org_prs


async def list_alerts(install_id: int | None, org_login: str, limit: int = 100) -> list[Alert]:
    out: list[Alert] = []
    out.extend(await _stuck_prs(install_id, org_login))
    out.extend(await _failing_check_runs(install_id, org_login))
    out.extend(await _dependabot_alerts(install_id, org_login))
    out.extend(await _code_scanning_alerts(install_id, org_login))
    return out[:limit]


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
