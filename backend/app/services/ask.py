"""Ask Anything — LLM-powered Q&A grounded on the active workspace.

Pipeline:
  1. Cache check — same (org, question) within TTL? Return cached.
  2. Search GitHub for relevant PRs/issues + code matching the question.
  3. Build a compact context string from those results.
  4. Ask Gemini to answer using *only* that context, with citations.
  5. Cache the response (Mongo TTL, 30 min) so re-asks are free.
  6. Return the answer + sources for the UI's citations rail.

Falls back to a deterministic "found N matches" summary if Gemini is
not configured. The frontend never has to branch — same shape always.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from app.clients import gemini
from app.clients.github import gh_for
from app.core.db import get_db
from app.models.schemas import AskAnswer, AskSourceGroup, AskSourceItem

ASK_CACHE_TTL = timedelta(minutes=30)


def _cache_key(org_login: str, repo: str | None, q: str) -> str:
    raw = f"{org_login.lower()}::{(repo or '').lower()}::{q.strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()


SYSTEM_PROMPT = """You are a senior engineer reviewing a GitHub organization's
recent activity for the user. Answer their question concisely (3-6 sentences
max), grounded ONLY in the provided GitHub data. If the data is insufficient
to answer, say so plainly. Cite sources inline as [#PR-NUMBER] or
[REPO/PATH] when referencing specific items. Never invent PRs, repos, or
people that are not present in the data. Be direct, no filler."""


async def ask(
    install_id: int | None,
    org_login: str,
    q: str,
    repo: str | None = None,
    limit: int = 10,
) -> AskAnswer:
    """Answer ``q`` using the active workspace's GitHub data, optionally
    LLM-summarized via Gemini. Result is cached for 30 min per (org, q)."""
    db = get_db()
    key = _cache_key(org_login, repo, q)
    cached = await db["ask_cache"].find_one({"key": key})
    if cached:
        return AskAnswer.model_validate(cached["payload"])

    scope = f"repo:{org_login}/{repo}" if repo else f"org:{org_login}"
    gh = gh_for(install_id)

    # 1. Pull search hits — issues/PRs and code in parallel-ish
    issues_data = await gh.get(
        "/search/issues", params={"q": f"{scope} {q}", "per_page": limit}
    )
    try:
        code_data = await gh.get(
            "/search/code", params={"q": f"{scope} {q}", "per_page": min(limit, 5)}
        )
    except Exception:
        code_data = {"items": []}

    pr_items = [
        AskSourceItem(
            t=f"#{i['number']} — {i['title']}",
            d=(i.get("body") or "")[:200],
            url=i["html_url"],
        )
        for i in issues_data.get("items", [])
    ]
    code_items = [
        AskSourceItem(
            t=f"{c['repository']['name']}/{c['path']}",
            d=c.get("name", ""),
            url=c.get("html_url"),
        )
        for c in code_data.get("items", [])
    ]

    sources = [
        AskSourceGroup(kind="prs_issues", items=pr_items),
        AskSourceGroup(kind="code", items=code_items),
    ]

    # 2. LLM answer (or fallback)
    if gemini.is_enabled() and (pr_items or code_items):
        answer = await _llm_answer(q, org_login, repo, issues_data, code_data)
    else:
        answer = _deterministic_answer(q, repo, pr_items, code_items)

    result = AskAnswer(
        q=q,
        answer=answer,
        sources=sources,
        followups=_default_followups(repo),
    )

    # Persist with TTL — Mongo will purge after expires_at.
    await db["ask_cache"].update_one(
        {"key": key},
        {
            "$set": {
                "key": key,
                "org": org_login.lower(),
                "repo": (repo or "").lower(),
                "q": q,
                "payload": result.model_dump(mode="json"),
                "expires_at": datetime.now(timezone.utc) + ASK_CACHE_TTL,
            }
        },
        upsert=True,
    )
    return result


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────
async def _llm_answer(
    q: str,
    org_login: str,
    repo: str | None,
    issues_data: dict[str, Any],
    code_data: dict[str, Any],
) -> str:
    items = issues_data.get("items", [])[:8]
    code = code_data.get("items", [])[:5]

    lines: list[str] = []
    lines.append(f"# Workspace: {org_login}{f' / {repo}' if repo else ''}")
    lines.append(f"# Question: {q}")
    lines.append("")
    if items:
        lines.append("## PRs / issues")
        for it in items:
            state = "merged" if it.get("pull_request", {}).get("merged_at") else it.get("state", "?")
            user = (it.get("user") or {}).get("login", "?")
            updated = it.get("updated_at", "")
            body = (it.get("body") or "").replace("\n", " ")[:240]
            lines.append(
                f"- #{it['number']} [{state}] by {user} ({updated[:10]}): "
                f"{it['title']}"
            )
            if body:
                lines.append(f"    {body}")
    if code:
        lines.append("")
        lines.append("## Code matches")
        for c in code:
            lines.append(f"- {c['repository']['name']}/{c['path']} — {c.get('name', '')}")
    context = "\n".join(lines)

    prompt = (
        f"{context}\n\n"
        "Answer the question above using only the data shown. "
        "Be concise. Cite items as [#N] or [repo/path]."
    )
    try:
        return (await gemini.generate(prompt, system=SYSTEM_PROMPT)).strip()
    except Exception as exc:  # pragma: no cover - LLM transient
        return (
            f"(AI unavailable — {exc}.) "
            f"Found {len(items)} PRs/issues and {len(code)} code matches."
        )


def _deterministic_answer(
    q: str,
    repo: str | None,
    prs: list[AskSourceItem],
    code: list[AskSourceItem],
) -> str:
    return (
        f"Found {len(prs)} PRs/issues and {len(code)} code matches for "
        f"\"{q}\"" + (f" in {repo}" if repo else "") + ". "
        "Open the items in the Sources panel for details."
    )


def _default_followups(repo: str | None) -> list[str]:
    if repo:
        return [
            f"Who has been most active in {repo} recently?",
            f"What's failing CI on {repo}?",
            "Any stuck PRs in this repo?",
        ]
    return [
        "Who has been most active recently?",
        "Which PRs are stuck waiting for review?",
        "What's failing CI right now?",
    ]
