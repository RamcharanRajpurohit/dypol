"""Incremental index pipeline — tenant-scoped (see ``app/rag/tenant.py``).

Works for both workspace modes: App installs index everything the
installation can read, public (open-source) workspaces index public repos
through the shared public client. The ``Tenant`` value object carries both
the storage namespace and the GitHub auth to use, so nothing below has to
care which mode it's running in.

Three entry points:
  * ``index_repo``     — code: walk the git tree, fetch each supported blob,
    cAST-chunk, embed in batches, upsert with a GitHub blob URL.
  * ``index_prose``    — discussions: recent PRs/issues/commits → compact
    "cards" → prose chunks → embed → upsert.
  * ``run_index_tick`` — the scheduler entry: pick a few installs/repos,
    drain dirty or backfill newest-pushed-first, all under a wall-clock +
    embed budget, fully resumable via cursors, isolated so one repo's
    failure never aborts the tick.

Everything runs the (sync) embedder/store calls in a thread so the event
loop stays free, and every repo is wrapped so a single failure is logged
and skipped, never fatal.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from app.clients.github import gh_for
from app.core.config import get_settings
from app.core.db import get_db
from app.rag.chunker import chunk_code, chunk_prose, lang_for_path
from app.rag.embeddings import get_embedder
from app.rag.models import Chunk, IndexCursor
from app.rag.state import drain_dirty, get_cursor, has_dirty, set_cursor
from app.rag.store import get_vector_store
from app.rag.tenant import Tenant, tenant_for

log = logging.getLogger("dypol.rag.ingest")

# Path fragments we never index (vendored, build output, minified, locks, bins).
_SKIP_FRAGMENTS: tuple[str, ...] = (
    "node_modules/",
    "/dist/",
    "/build/",
    "/vendor/",
    "/.git/",
    "/__pycache__/",
    "/target/",
    "/.venv/",
    "site-packages/",
    ".min.",
)
_SKIP_SUFFIXES: tuple[str, ...] = (
    ".lock",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".pdf",
    ".zip",
    ".gz",
    ".tar",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".mp4",
    ".mp3",
    ".bin",
    ".so",
    ".dll",
    ".class",
    ".jar",
    ".wasm",
)
_SKIP_NAMES: tuple[str, ...] = (
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Cargo.lock",
    "go.sum",
)


@dataclass(slots=True)
class IndexBudget:
    """Wall-clock + embed cap so a tick can't run away."""

    max_seconds: float = 90.0
    max_embeds: int = 2000
    _started: float = field(default_factory=time.monotonic)
    _embedded: int = 0

    def time_left(self) -> float:
        return self.max_seconds - (time.monotonic() - self._started)

    def exhausted(self) -> bool:
        return self.time_left() <= 0 or self._embedded >= self.max_embeds

    def add(self, n: int) -> None:
        self._embedded += n


def _should_skip(path: str, size: int | None) -> bool:
    lower = "/" + path.lower()
    name = path.rsplit("/", 1)[-1]
    if name in _SKIP_NAMES:
        return True
    if any(frag in lower for frag in _SKIP_FRAGMENTS):
        return True
    if any(lower.endswith(sfx) for sfx in _SKIP_SUFFIXES):
        return True
    if lang_for_path(path) is None:
        return True
    return bool(size is not None and size > get_settings().rag_max_file_bytes)


async def _embed_and_upsert(
    tenant_id: int,
    chunks: list[Chunk],
    kind: str,
    budget: IndexBudget,
) -> tuple[int, str, int]:
    """Embed ``chunks`` in batches and upsert them. Returns
    (n_upserted, embedder_model, dim). No-op (0, "", 0) if no embedder."""
    if not chunks:
        return 0, "", 0
    embedder = get_embedder("code" if kind == "code" else "prose")
    if embedder is None:
        return 0, "", 0

    store = get_vector_store(tenant_id)
    batch = get_settings().rag_embed_batch
    total = 0
    for i in range(0, len(chunks), batch):
        if budget.exhausted():
            break
        sub = chunks[i : i + batch]
        texts = [c.text for c in sub]
        try:
            vectors = await asyncio.to_thread(embedder.embed, texts)
        except Exception as exc:
            log.warning("embed batch failed (%s): %s", kind, exc)
            continue
        if not vectors or len(vectors) != len(sub):
            continue
        ids = [_chunk_id(tenant_id, c, j) for j, c in enumerate(sub, start=i)]
        try:
            await asyncio.to_thread(store.upsert, sub, vectors, ids)
        except Exception as exc:
            log.warning("upsert failed (%s): %s", kind, exc)
            continue
        total += len(sub)
        budget.add(len(sub))
    return total, embedder.model_id, embedder.dim


def _chunk_id(tenant_id: int, chunk: Chunk, ordinal: int) -> str:
    """Stable id so re-indexing the same symbol overwrites in place."""
    parts = [
        str(tenant_id),
        chunk.repo,
        chunk.kind,
        chunk.path or "",
        str(chunk.ref_number or ""),
        str(chunk.start_line or ""),
        str(chunk.symbol or ordinal),
    ]
    return "::".join(parts)


def _blob_url(repo_full_name: str, ref: str | None, path: str, line: int | None) -> str:
    branch = ref or "HEAD"
    base = f"https://github.com/{repo_full_name}/blob/{branch}/{path}"
    return f"{base}#L{line}" if line else base


# ──────────────────────────────────────────────────────────────────────
# Code indexing
# ──────────────────────────────────────────────────────────────────────
async def index_repo(
    tenant: Tenant, repo_full_name: str, budget: IndexBudget
) -> int:
    """Index a repo's source tree. Returns the number of chunks upserted."""
    gh = gh_for(tenant.install_id)
    try:
        meta = await gh.get(f"/repos/{repo_full_name}")
    except Exception as exc:
        log.info("index_repo %s: repo meta failed: %s", repo_full_name, exc)
        return 0
    default_branch = meta.get("default_branch") or "HEAD"
    head_sha = None

    try:
        branch = await gh.get(
            f"/repos/{repo_full_name}/branches/{default_branch}"
        )
        head_sha = (branch.get("commit") or {}).get("sha")
    except Exception:
        head_sha = None

    # Skip if the cursor already covers this head.
    cursor = await get_cursor(tenant.id, repo_full_name)
    if cursor and head_sha and cursor.last_sha == head_sha:
        log.debug("index_repo %s: up to date (%s)", repo_full_name, head_sha[:7])
        return 0

    try:
        tree = await gh.get(
            f"/repos/{repo_full_name}/git/trees/{head_sha or default_branch}",
            params={"recursive": "1"},
        )
    except Exception as exc:
        log.info("index_repo %s: tree fetch failed: %s", repo_full_name, exc)
        return 0

    entries = [
        e
        for e in (tree.get("tree") or [])
        if e.get("type") == "blob"
        and not _should_skip(e.get("path", ""), e.get("size"))
    ]

    total = 0
    model = ""
    dim = 0
    for entry in entries:
        if budget.exhausted():
            log.info("index_repo %s: budget exhausted, stopping", repo_full_name)
            break
        path = entry["path"]
        text = await _fetch_blob_text(gh, repo_full_name, path, entry.get("sha"))
        if not text:
            continue
        chunks = chunk_code(repo_full_name, path, text, sha=entry.get("sha"))
        for c in chunks:
            c.url = _blob_url(repo_full_name, default_branch, path, c.start_line)
        n, model, dim = await _embed_and_upsert(tenant.id, chunks, "code", budget)
        total += n

    new_cursor = IndexCursor(
        install_id=tenant.id,
        repo=repo_full_name,
        last_sha=head_sha,
        chunk_count=(cursor.chunk_count if cursor else 0) + total,
        embedder_model=model or (cursor.embedder_model if cursor else ""),
        dim=dim or (cursor.dim if cursor else 0),
    )
    await set_cursor(new_cursor)
    log.info("index_repo %s: upserted %d code chunks", repo_full_name, total)
    return total


async def _fetch_blob_text(
    gh: Any, repo_full_name: str, path: str, sha: str | None
) -> str | None:
    """Fetch + base64-decode a blob via the contents API. Returns None for
    binary or on error."""
    try:
        data = await gh.get(f"/repos/{repo_full_name}/contents/{path}")
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if data.get("encoding") != "base64" or not data.get("content"):
        return None
    try:
        raw = base64.b64decode(data["content"])
    except Exception:
        return None
    if b"\x00" in raw[:4096]:  # crude binary sniff
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


# ──────────────────────────────────────────────────────────────────────
# Prose indexing (PRs / issues / commits)
# ──────────────────────────────────────────────────────────────────────
async def index_prose(
    tenant: Tenant, repo_full_name: str, budget: IndexBudget
) -> int:
    """Index recent discussion as compact cards. Returns chunks upserted."""
    gh = gh_for(tenant.install_id)
    s = get_settings()
    since = (
        datetime.now(UTC) - timedelta(days=s.rag_prose_window_days)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    chunks: list[Chunk] = []

    # PRs + issues (the issues endpoint returns both).
    try:
        issues = await gh.collect(
            f"/repos/{repo_full_name}/issues",
            params={"state": "all", "since": since, "sort": "updated"},
            max_pages=3,
        )
    except Exception as exc:
        log.debug("index_prose %s: issues failed: %s", repo_full_name, exc)
        issues = []
    for it in issues:
        if not isinstance(it, dict):
            continue
        is_pr = "pull_request" in it
        number = it.get("number")
        title = it.get("title") or ""
        body = (it.get("body") or "")[:1500]
        kind_label = "PR" if is_pr else "Issue"
        card = f"{kind_label} #{number}: {title}\nstate={it.get('state')}\n\n{body}"
        for c in chunk_prose(
            card,
            repo=repo_full_name,
            ref_number=number,
            url=it.get("html_url"),
            symbol=f"{kind_label.lower()}-{number}",
        ):
            chunks.append(c)

    # Commits.
    try:
        commits = await gh.collect(
            f"/repos/{repo_full_name}/commits",
            params={"since": since},
            max_pages=2,
        )
    except Exception as exc:
        log.debug("index_prose %s: commits failed: %s", repo_full_name, exc)
        commits = []
    for cm in commits:
        if not isinstance(cm, dict):
            continue
        commit = cm.get("commit") or {}
        message = (commit.get("message") or "")[:1000]
        sha = cm.get("sha", "")
        if not message.strip():
            continue
        card = f"Commit {sha[:7]}: {message}"
        for c in chunk_prose(
            card,
            repo=repo_full_name,
            url=cm.get("html_url"),
            sha=sha,
            symbol=f"commit-{sha[:7]}",
        ):
            chunks.append(c)

    n, _model, _dim = await _embed_and_upsert(tenant.id, chunks, "prose", budget)
    log.info("index_prose %s: upserted %d prose chunks", repo_full_name, n)
    return n


# ──────────────────────────────────────────────────────────────────────
# Scheduler entry
# ──────────────────────────────────────────────────────────────────────
async def _tenants_to_process() -> list[Tenant]:
    """Every workspace worth indexing this tick, de-duplicated by tenant id.

    Public workspaces are included only when a ``GITHUB_PAT`` is configured:
    indexing costs one request per blob, and the anonymous budget is 60
    requests/hour shared by the whole deployment — a single repo would eat it
    and starve the live agent. With a PAT there's 5,000/hour to work with.
    """
    db = get_db()
    seen: set[int] = set()
    out: list[Tenant] = []
    allow_public = bool(get_settings().github_pat)
    skipped_public = 0

    async for doc in db["installations"].find({}):
        tenant = tenant_for(doc)
        if tenant is None or tenant.id in seen:
            continue
        if tenant.is_public and not allow_public:
            skipped_public += 1
            continue
        seen.add(tenant.id)
        out.append(tenant)

    if skipped_public:
        log.info(
            "rag: skipping %d public workspace(s) — set GITHUB_PAT to index them "
            "(anonymous budget is 60 req/hr)",
            skipped_public,
        )
    return out


async def _repos_for_tenant(tenant: Tenant, cap: int) -> list[str]:
    """Pick repos to index: dirty ones first, then newest-pushed backfill."""
    repos: list[str] = []
    seen: set[str] = set()

    # 1) Dirty queue (coalesced webhook signals). Public tenants never have
    #    entries here — no install means no webhook delivery — so they always
    #    fall through to the backfill below.
    if await has_dirty(tenant.id):
        for entry in await drain_dirty(tenant.id, limit=cap * 4):
            r = entry.get("repo")
            if r and r not in seen:
                seen.add(r)
                repos.append(r)

    # 2) Backfill newest-pushed first.
    if len(repos) < cap:
        candidates = await _candidate_repos(tenant)
        candidates.sort(key=lambda r: r.get("pushed_at") or "", reverse=True)
        for r in candidates:
            name = r.get("full_name")
            if name and name not in seen:
                seen.add(name)
                repos.append(name)
            if len(repos) >= cap:
                break

    return repos[:cap]


async def _candidate_repos(tenant: Tenant) -> list[dict[str, Any]]:
    """Raw repo listings for a tenant — installation scope, or public listing."""
    gh = gh_for(tenant.install_id)
    if tenant.is_public:
        path = (
            f"/orgs/{tenant.login}/repos"
            if tenant.is_org
            else f"/users/{tenant.login}/repos"
        )
        try:
            listing = await gh.collect(path, params={"per_page": 100}, max_pages=2)
        except Exception:
            return []
        return [r for r in listing if isinstance(r, dict) and r.get("full_name")]

    try:
        listing = await gh.collect("/installation/repositories", max_pages=2)
    except Exception:
        return []
    # /installation/repositories returns {"repositories":[...]} per page;
    # collect() yields the dict(s).
    candidates: list[dict[str, Any]] = []
    for page in listing:
        if isinstance(page, dict) and "repositories" in page:
            candidates.extend(page["repositories"])
        elif isinstance(page, dict) and page.get("full_name"):
            candidates.append(page)
    return candidates


async def run_index_tick() -> dict[str, Any]:
    """One incremental pass. Safe to call from the scheduler on an interval.

    Returns a small stats dict for logging/observability. Never raises — a
    failing install or repo is isolated and recorded in ``errors``.
    """
    from app.rag import is_rag_enabled

    if not is_rag_enabled():
        return {"skipped": "rag_disabled"}

    s = get_settings()
    budget = IndexBudget(max_seconds=max(30.0, s.rag_index_interval_min * 1.0))
    stats: dict[str, Any] = {
        "installs": 0,
        "public_tenants": 0,
        "repos": 0,
        "code_chunks": 0,
        "prose_chunks": 0,
        "errors": [],
    }

    tenants = await _tenants_to_process()
    for tenant in tenants:
        if budget.exhausted():
            break
        stats["installs"] += 1
        if tenant.is_public:
            stats["public_tenants"] += 1
        try:
            repos = await _repos_for_tenant(tenant, s.rag_max_repos_per_tick)
        except Exception as exc:
            stats["errors"].append(f"tenant {tenant.id} ({tenant.login}): {exc}")
            continue

        for repo in repos:
            if budget.exhausted():
                break
            try:
                stats["code_chunks"] += await index_repo(tenant, repo, budget)
                if not budget.exhausted():
                    stats["prose_chunks"] += await index_prose(
                        tenant, repo, budget
                    )
                stats["repos"] += 1
            except Exception as exc:  # isolate per-repo failure
                log.warning("index tick: repo %s failed: %s", repo, exc)
                stats["errors"].append(f"{repo}: {exc}")

    log.info("rag index tick: %s", {k: v for k, v in stats.items() if k != "errors"})
    return stats
