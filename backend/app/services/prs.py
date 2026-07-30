from __future__ import annotations

from datetime import datetime
from typing import Any

from app.clients.github import gh_for
from app.models.schemas import PR


def _parse_dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def _to_pr(repo: str, raw: dict[str, Any]) -> PR:
    state: str = raw.get("state", "open")
    if raw.get("merged_at"):
        state = "merged"
    return PR(
        repo=repo,
        number=raw["number"],
        title=raw["title"],
        state=state,  # type: ignore[arg-type]
        author=(raw.get("user") or {}).get("login"),
        created_at=_parse_dt(raw["created_at"]) or datetime.utcnow(),
        updated_at=_parse_dt(raw["updated_at"]) or datetime.utcnow(),
        merged_at=_parse_dt(raw.get("merged_at")),
        additions=raw.get("additions"),
        deletions=raw.get("deletions"),
        review_count=raw.get("review_comments", 0),
        comments=raw.get("comments", 0),
        draft=raw.get("draft", False),
        html_url=raw["html_url"],
    )


async def list_repo_prs(
    install_id: int | None, full_name: str, state: str = "all", limit: int = 50
) -> list[PR]:
    raw = await gh_for(install_id).collect(
        f"/repos/{full_name}/pulls",
        params={"state": state, "sort": "updated", "direction": "desc"},
        max_pages=max(1, limit // 100 + 1),
    )
    repo_short = full_name.split("/")[-1]
    return [_to_pr(repo_short, r) for r in raw[:limit]]


async def list_org_prs(
    install_id: int | None, org_login: str, state: str = "open", limit: int = 100
) -> list[PR]:
    """Search-API across the org for PRs. Auth uses the install token."""
    q = f"org:{org_login} is:pr is:{state}"
    data = await gh_for(install_id).get(
        "/search/issues", params={"q": q, "per_page": min(limit, 100)}
    )
    items = data.get("items", [])
    out: list[PR] = []
    for raw in items[:limit]:
        repo_url: str = raw.get("repository_url", "")
        repo_name = repo_url.rsplit("/", 1)[-1]
        out.append(_to_pr(repo_name, {**raw, "html_url": raw["html_url"]}))
    return out


async def get_pr_detail(install_id: int | None, full_name: str, number: int) -> PR:
    raw = await gh_for(install_id).get(f"/repos/{full_name}/pulls/{number}")
    return _to_pr(full_name.split("/")[-1], raw)
