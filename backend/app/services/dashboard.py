"""Dashboard composition — pulls together repos, PRs, alerts, contributors,
and computes KPIs (current vs previous 7-day window) for the headline UI.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.clients.github import gh_for
from app.core.errors import GitHubError
from app.models.schemas import (
    Alert,
    Contributor,
    DashboardSummary,
    Kpi,
    Repo,
)
from app.services.activity import list_org_events
from app.services.alerts import list_alerts
from app.services.repos import list_org_repos, repo_scan_cap


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────
def _delta(current: float, previous: float) -> tuple[float, float | None, str, str]:
    """Returns (delta, delta_pct, direction, sentiment-default).

    sentiment defaults to neutral; callers override based on whether "up" is
    actually good for that metric (e.g. up commits = good, up cycle time = bad).
    """
    delta = current - previous
    if previous > 0:
        pct = round((delta / previous) * 100, 1)
    else:
        pct = None
    if abs(delta) < 0.01:
        return (0, pct, "flat", "neutral")
    return (round(delta, 1), pct, "up" if delta > 0 else "down", "neutral")


async def _search_count(install_id: int | None, q: str) -> int:
    try:
        data = await gh_for(install_id).get(
            "/search/issues", params={"q": q, "per_page": 1}
        )
        return int(data.get("total_count", 0))
    except GitHubError:
        return 0


# ──────────────────────────────────────────────────────────────────
# Headline narrative — deterministic, template-based
# ──────────────────────────────────────────────────────────────────
def _headline(org: str, prs_merged: Kpi, active_devs: int) -> str:
    if prs_merged.value == 0:
        return f"{org} hasn't merged any PRs this week — quiet stretch."
    direction_word = {
        "up": "up",
        "down": "down",
        "flat": "in line with",
    }[prs_merged.direction]
    if prs_merged.delta_pct is None:
        compare = "no prior baseline"
    elif prs_merged.direction == "flat":
        compare = "in line with last week"
    else:
        compare = f"{direction_word} {abs(prs_merged.delta_pct)}% from last week"
    devs_phrase = (
        f"{active_devs} devs active" if active_devs else "no active contributors"
    )
    return (
        f"{org} shipped {int(prs_merged.value)} PRs this week, "
        f"{compare}. {devs_phrase}."
    )


# ──────────────────────────────────────────────────────────────────
# Top contributors — fetch commits in the last 7 days across top repos
# ──────────────────────────────────────────────────────────────────
async def _top_contributors(
    install_id: int | None, repos: list[Repo], since_iso: str, limit: int = 5
) -> list[Contributor]:
    stats: dict[str, dict[str, Any]] = {}
    gh = gh_for(install_id)
    for repo in repos[: repo_scan_cap(install_id, install_cap=10)]:
        try:
            commits = await gh.collect(
                f"/repos/{repo.full_name}/commits",
                params={"since": since_iso},
                max_pages=1,
                per_page=100,
            )
        except Exception:
            continue
        for c in commits:
            login = (c.get("author") or {}).get("login")
            if not login:
                continue
            stat = stats.setdefault(
                login,
                {
                    "login": login,
                    "name": (c.get("commit") or {}).get("author", {}).get("name"),
                    "avatar_url": (c.get("author") or {}).get("avatar_url", ""),
                    "commits": 0,
                },
            )
            stat["commits"] += 1
    contribs = sorted(stats.values(), key=lambda s: s["commits"], reverse=True)[:limit]
    return [
        Contributor(
            login=s["login"],
            name=s.get("name"),
            avatar_url=s.get("avatar_url") or "",
            commits=s["commits"],
            score=float(s["commits"]),
        )
        for s in contribs
    ]


# ──────────────────────────────────────────────────────────────────
# Curated alerts — max 3, sorted by severity then recency
# ──────────────────────────────────────────────────────────────────
_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _curate_alerts(alerts: list[Alert], limit: int = 3) -> list[Alert]:
    return sorted(
        alerts,
        key=lambda a: (
            _SEVERITY_ORDER.get(a.severity, 99),
            -(a.created_at.timestamp() if a.created_at else 0),
        ),
    )[:limit]


# ──────────────────────────────────────────────────────────────────
# Top-level builder
# ──────────────────────────────────────────────────────────────────
async def build_dashboard(install: dict[str, Any]) -> DashboardSummary:
    install_id = install.get("install_id")
    org = install.get("account_login_display") or install["account_login"]
    org_lower = install["account_login"].lower()
    mode = install.get("mode", "install")

    now = datetime.now(timezone.utc)
    week_start = now - timedelta(days=7)
    prev_start = now - timedelta(days=14)
    week_iso = week_start.isoformat()
    week_date = week_start.date().isoformat()
    prev_date = prev_start.date().isoformat()

    # Parallel-able stats — keep simple sequential for now (cache covers).
    prs_merged_now = await _search_count(
        install_id, f"org:{org_lower} is:pr is:merged merged:>={week_date}"
    )
    prs_merged_prev = await _search_count(
        install_id,
        f"org:{org_lower} is:pr is:merged merged:{prev_date}..{week_date}",
    )
    prs_opened_now = await _search_count(
        install_id, f"org:{org_lower} is:pr created:>={week_date}"
    )
    prs_opened_prev = await _search_count(
        install_id,
        f"org:{org_lower} is:pr created:{prev_date}..{week_date}",
    )

    repos = await list_org_repos(install_id, org_lower)
    repos_sorted = sorted(
        repos,
        key=lambda r: r.pushed_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    contribs = await _top_contributors(install_id, repos_sorted, week_iso, limit=5)
    active_devs_now = len(contribs)

    alerts_all = await list_alerts(install_id, org_lower, limit=50)
    events = await list_org_events(install, limit=8)

    # ── KPIs ──
    pr_merged_delta, pr_merged_pct, pr_merged_dir, _ = _delta(
        prs_merged_now, prs_merged_prev
    )
    pr_opened_delta, pr_opened_pct, pr_opened_dir, _ = _delta(
        prs_opened_now, prs_opened_prev
    )
    active_repos = sum(1 for r in repos if r.pushed_at and r.pushed_at >= week_start)

    kpis = [
        Kpi(
            label="PRs merged",
            value=prs_merged_now,
            delta=pr_merged_delta,
            delta_pct=pr_merged_pct,
            direction=pr_merged_dir,
            sentiment="good"
            if pr_merged_dir == "up"
            else "bad"
            if pr_merged_dir == "down"
            else "neutral",
        ),
        Kpi(
            label="PRs opened",
            value=prs_opened_now,
            delta=pr_opened_delta,
            delta_pct=pr_opened_pct,
            direction=pr_opened_dir,
            sentiment="neutral",
        ),
        Kpi(
            label="Active devs",
            value=active_devs_now,
            sentiment="neutral",
        ),
        Kpi(
            label="Active repos",
            value=active_repos,
            unit=f"of {len(repos)}",
            sentiment="neutral",
        ),
    ]

    headline = _headline(org, kpis[0], active_devs_now)
    period_label = f"Week of {week_start.strftime('%b %-d')}"

    return DashboardSummary(
        org=org,
        org_type=install.get("account_type"),
        mode=mode,
        period_label=period_label,
        headline=headline,
        kpis=kpis,
        repos_total=len(repos),
        repos=repos_sorted[:8],
        top_contributors=contribs,
        top_alerts=_curate_alerts(alerts_all),
        alerts_total=len(alerts_all),
        recent_activity=events,
    )
