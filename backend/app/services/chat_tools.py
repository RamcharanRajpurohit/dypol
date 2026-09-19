"""Tool registry — minimal, generic GitHub-API tools for the agent.

Philosophy: instead of pre-defining one tool per task ("list_top_contributors",
"list_alerts", etc), we expose **the GitHub API itself** as 4 generic tools.
The model already knows GitHub's REST surface from training and can compose
calls — that gives it the freedom to answer anything users ask, without us
needing to add a new tool every time a new question shape comes up.

Tools:
  1. ``github_get``       — GET any GitHub REST path (read-only, allowlisted).
  2. ``github_search``    — GitHub's /search/{type} endpoints.
  3. ``github_graphql``   — Single GraphQL query for multi-resource fetches.
  4. ``workspace_info``   — Tells the agent which org/install it's on, plus
                            current rate-limit budget so it can be efficient.

Safety:
  * Only GET method allowed at the HTTP layer.
  * Path allowlist blocks ``/user/*`` write endpoints and admin routes.
  * Response payloads >50 KB are truncated before being passed back to the
    model — saves tokens and avoids context bloat.
"""
from __future__ import annotations

import json
import re
from typing import Any, Awaitable, Callable

from google.genai import types as genai_types

from app.clients.github import gh_for, gh_public  # noqa: F401

ToolHandler = Callable[..., Awaitable[Any]]

# Endpoints the agent is allowed to call. Pattern-based: ^prefix → ok.
# Anything not matching is rejected with a friendly error so the model can
# try a different approach.
_ALLOWED_PATH_PREFIXES: tuple[str, ...] = (
    # Read-only org/install/repo data
    "/installation/",
    "/repos/",
    "/orgs/",
    "/users/",
    # Search APIs
    "/search/",
    # Rate-limit introspection
    "/rate_limit",
    # User-facing only — read-only profile lookup is fine
    "/user/orgs",
)

# Paths to explicitly block even if they match a prefix above.
_BLOCKED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"/repos/[^/]+/[^/]+/(merges|transfer|delete)\b"),
    re.compile(r"/orgs/[^/]+/(invitations|migrations)\b"),
)

# Cap the per-tool response so a huge payload can't blow the context window.
# 6 KB was sized for Groq's tight 8k-tokens/min free tier and clipped large
# (but useful) lists like "all repos" down to a single item. With slimming
# (see _slim_rest_list) + modern context windows, 24 KB comfortably fits a
# full slimmed repo/PR/commit list while still bounding pathological payloads.
_MAX_RESPONSE_BYTES = 24_000


# ──────────────────────────────────────────────────────────────────
# Tool descriptions — single source of truth shared by the legacy Gemini
# declarations, the legacy OpenAI specs, AND the new LangChain StructuredTool
# wrappers in app/agents/tools.py. Keep these in one place so the model sees
# identical guidance regardless of which adapter is active.
# ──────────────────────────────────────────────────────────────────
TOOL_DESCRIPTIONS: dict[str, str] = {
    "github_get": (
        "Make a GET request to any GitHub REST API endpoint using the "
        "active workspace's auth. You know the GitHub REST API — "
        "compose paths yourself.\n\n"
        "Examples:\n"
        "  github_get('/installation/repositories') — list repos, INSTALL mode\n"
        "  github_get('/orgs/{org}/repos') — list repos, PUBLIC mode "
        "(/installation/* is unavailable there; see workspace_info)\n"
        "  github_get('/repos/{owner}/{repo}') — repo metadata\n"
        "  github_get('/repos/{owner}/{repo}/pulls', {'state': 'open'})\n"
        "  github_get('/repos/{owner}/{repo}/commits', {'since': '2026-01-01'})\n"
        "  github_get('/repos/{owner}/{repo}/contributors')\n"
        "  github_get('/orgs/{org}/members')\n\n"
        "Read-only. Returns JSON (truncated if huge). 404s and other "
        "errors come back as {\"error\": \"...\"} so you can recover.\n\n"
        "Reading a FILE: github_get('/repos/{o}/{r}/contents/{file_path}') "
        "returns the file decoded into numbered lines. For LARGE files it "
        "returns a 200-line window plus total_lines; page through by calling "
        "again with params {\"start_line\": N} (and optional max_lines). "
        "For LISTS that come back truncated (_truncated:true), narrow with "
        "per_page / filters or fetch a single resource."
    ),
    "github_search": (
        "Search GitHub. Wraps /search/{type}.\n\n"
        "Examples:\n"
        "  github_search('issues', 'org:vercel is:pr is:merged author:lee')\n"
        "  github_search('code', 'org:vercel useEffect language:typescript')\n"
        "  github_search('repositories', 'org:vercel topic:framework')\n\n"
        "Returns up to 30 hits with a total_count."
    ),
    "workspace_info": (
        "Returns information about the active workspace: org login, "
        "account type (User/Organization), mode (install/public), and "
        "the current GitHub API rate-limit budget. Call this first if "
        "you don't know the org name, or if you suspect rate limits "
        "are tight."
    ),
    "web_search": (
        "Search the public web for current, external information the GitHub "
        "API can't provide: library/framework documentation, release notes, "
        "CVEs and security advisories, best-practice guidance, error messages, "
        "or anything happening outside this org's repos. Use it to enrich "
        "answers with up-to-date external context, then cite the source URLs. "
        "Returns a list of {title, url, content} results."
    ),
    "semantic_search": (
        "Semantic (meaning-based) search over THIS workspace's indexed code, "
        "PRs, issues, and commit messages. Use it to DISCOVER relevant files "
        "or discussions when you don't know the exact path or keywords "
        "(e.g. 'where is rate limiting handled', 'past PRs about the auth "
        "refactor'). Returns ranked POINTERS (repo, path, line range, URL) — "
        "then call github_get to read the authoritative, current content of "
        "whatever it points to. Returns an empty list if nothing is indexed "
        "yet; if so, fall back to github_search / github_get."
    ),
    "python_exec": (
        "Run a Python snippet to CALCULATE, analyze, or transform data — "
        "averages, percentiles, cycle-time math, grouping, sorting, counting, "
        "date arithmetic, formatting tables. Use this instead of mental "
        "arithmetic (error-prone).\n"
        "IMPORTANT: the sandbox is EMPTY — there are NO pre-existing variables "
        "and NO access to previous tool results. You MUST paste the data you "
        "need directly INTO your code as a literal. There is no "
        "`github_get_response`, `output`, or similar — define your own data.\n"
        "Available: `math`, `statistics`, `json`, `re`, `datetime`, `collections` "
        "(import or use directly) + safe builtins. NO file/network/os access.\n"
        "Assign the answer to `result` (returned as JSON) or print() it.\n"
        "Example — find the most recent of some repos:\n"
        "  repos=[{'name':'a','pushed_at':'2026-01-02'},{'name':'b','pushed_at':'2026-03-01'}]\n"
        "  result=max(repos, key=lambda r: r['pushed_at'])['name']"
    ),
    "summarize": (
        "Compress long content into a concise summary via a fast model — use "
        "before reasoning over very long inputs (e.g. 200 commit messages, a "
        "huge file, a long PR thread) so you don't blow your context. Pass the "
        "`text` and optional `instructions` (what to focus on). Returns "
        "{summary: ...}."
    ),
    "current_datetime": (
        "Get the current UTC date/time plus pre-computed 'since' dates for 7/30/"
        "90-day windows. Call this FIRST whenever a question uses relative time "
        "('this week', 'last month', 'recently', 'this quarter') so you filter "
        "GitHub with real ISO dates instead of guessing."
    ),
    "remember": (
        "Save a durable fact about THIS user or workspace to long-term memory "
        "that persists across ALL their future chats — preferences ('prefers "
        "terse answers'), context ('we use trunk-based dev', 'release day is "
        "Thursday'), or recurring focus ('cares most about the billing team'). "
        "Use it when the user states a lasting preference or fact you'd want to "
        "recall next time. Do NOT save one-off question details or secrets. "
        "Optional `category`: fact | preference | context."
    ),
    "github_graphql": (
        "Run a GitHub GraphQL (v4) read-only query for things the REST API "
        "can't do or that need many resources in one round-trip. The KILLER use "
        "is line-level BLAME — who last changed each line of a file:\n"
        "  query($o:String!,$r:String!){repository(owner:$o,name:$r){"
        "object(expression:\"HEAD:path/to/file.py\"){... on Blob{blame(...){"
        "ranges{startingLine endingLine commit{author{name} committedDate "
        "messageHeadline oid}}}}}}}\n"
        "Also good for: a PR's full review thread, cross-repo rollups, or "
        "fetching nested fields in one call. Pass `query` and optional "
        "`variables`. Read-only — never use mutations."
    ),
}


# ──────────────────────────────────────────────────────────────────
# Tool declarations — provider-agnostic source of truth.
#
# We define each tool once as a plain dict, then convert to whatever
# schema the active provider expects. Groq uses OpenAI's tool format;
# Gemini uses google-genai FunctionDeclaration.
# ──────────────────────────────────────────────────────────────────
_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "github_get",
        "description": TOOL_DESCRIPTIONS["github_get"],
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "API path starting with /. e.g. '/repos/vercel/next.js'",
                },
                "params": {
                    "type": "object",
                    "description": (
                        "Optional query params. e.g. {\"per_page\": 50, "
                        "\"state\": \"open\"}. Strings/numbers only."
                    ),
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "github_search",
        "description": TOOL_DESCRIPTIONS["github_search"],
        "parameters": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["issues", "code", "repositories", "users", "commits"],
                },
                "query": {
                    "type": "string",
                    "description": (
                        "GitHub search syntax. ALWAYS scope with org:{login} "
                        "or repo:{owner}/{repo} for the active workspace."
                    ),
                },
                "per_page": {
                    "type": "integer",
                    "description": "1-100, default 30.",
                },
            },
            "required": ["type", "query"],
        },
    },
    {
        "name": "workspace_info",
        "description": TOOL_DESCRIPTIONS["workspace_info"],
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
]


def build_openai_tools() -> list[dict[str, Any]]:
    """OpenAI/Groq-style tools array."""
    return [{"type": "function", "function": spec} for spec in _TOOL_SPECS]


def build_tool_declarations() -> list[genai_types.FunctionDeclaration]:
    """Legacy: gemini-style. Used by the Gemini fallback path."""
    return [
        genai_types.FunctionDeclaration(
            name="github_get",
            description=TOOL_DESCRIPTIONS["github_get"],
            parameters=genai_types.Schema(
                type=genai_types.Type.OBJECT,
                properties={
                    "path": genai_types.Schema(
                        type=genai_types.Type.STRING,
                        description=(
                            "API path starting with /. e.g. '/repos/vercel/next.js'"
                        ),
                    ),
                    "params": genai_types.Schema(
                        type=genai_types.Type.OBJECT,
                        description=(
                            "Optional query params. e.g. {\"per_page\": 50, "
                            "\"state\": \"open\"}. Strings/numbers only."
                        ),
                    ),
                },
                required=["path"],
            ),
        ),
        genai_types.FunctionDeclaration(
            name="github_search",
            description=TOOL_DESCRIPTIONS["github_search"],
            parameters=genai_types.Schema(
                type=genai_types.Type.OBJECT,
                properties={
                    "type": genai_types.Schema(
                        type=genai_types.Type.STRING,
                        enum=["issues", "code", "repositories", "users", "commits"],
                    ),
                    "query": genai_types.Schema(
                        type=genai_types.Type.STRING,
                        description=(
                            "GitHub search syntax. ALWAYS scope with org:{login} "
                            "or repo:{owner}/{repo} for the active workspace."
                        ),
                    ),
                    "per_page": genai_types.Schema(
                        type=genai_types.Type.INTEGER,
                        description="1-100, default 30.",
                    ),
                },
                required=["type", "query"],
            ),
        ),
        genai_types.FunctionDeclaration(
            name="workspace_info",
            description=TOOL_DESCRIPTIONS["workspace_info"],
            parameters=genai_types.Schema(
                type=genai_types.Type.OBJECT,
                properties={},
            ),
        ),
    ]


# ──────────────────────────────────────────────────────────────────
# Handlers
# ──────────────────────────────────────────────────────────────────
def _path_allowed(path: str) -> bool:
    if not path.startswith("/"):
        return False
    if not any(path.startswith(p) for p in _ALLOWED_PATH_PREFIXES):
        return False
    if any(p.search(path) for p in _BLOCKED_PATTERNS):
        return False
    return True


# How many lines of a large file to return per window.
_FILE_WINDOW_LINES = 200


def _maybe_file_window(data: Any, params: dict[str, Any]) -> dict[str, Any] | None:
    """If ``data`` is a GitHub file-content response, decode it and return a
    line-window so a LARGE file can be read in pages instead of byte-clipped.

    Returns ``None`` when ``data`` isn't a single decodable text file (so the
    caller falls back to ordinary ``_truncate``). Honors ``params``:
      * ``start_line`` (1-based, default 1) — where the window begins.
      * ``max_lines``  (default 200)        — window size.
    The model pages a big file by re-calling github_get with a higher
    ``start_line``. Binary/huge blobs return a clear, recoverable note.
    """
    if not isinstance(data, dict):
        return None
    if data.get("type") != "file" or data.get("encoding") != "base64":
        return None
    content_b64 = data.get("content")
    if not isinstance(content_b64, str):
        return None

    import base64

    try:
        raw_bytes = base64.b64decode(content_b64)
    except Exception:
        return None
    # Reject obvious binary (NUL byte) — not useful to the model as text.
    if b"\x00" in raw_bytes[:4096]:
        return {
            "path": data.get("path"),
            "size": data.get("size"),
            "sha": data.get("sha"),
            "note": "Binary file — not returned as text.",
            "html_url": data.get("html_url"),
        }
    try:
        text = raw_bytes.decode("utf-8", errors="replace")
    except Exception:
        return None

    lines = text.splitlines()
    total = len(lines)
    try:
        start = max(int(params.get("start_line", 1)), 1)
    except (TypeError, ValueError):
        start = 1
    try:
        window = min(max(int(params.get("max_lines", _FILE_WINDOW_LINES)), 1), 800)
    except (TypeError, ValueError):
        window = _FILE_WINDOW_LINES

    end = min(start - 1 + window, total)
    slice_lines = lines[start - 1 : end]
    # Number the lines so the model can cite path:line accurately.
    numbered = "\n".join(
        f"{start + i}\t{ln}" for i, ln in enumerate(slice_lines)
    )
    out: dict[str, Any] = {
        "path": data.get("path"),
        "sha": data.get("sha"),
        "total_lines": total,
        "showing_lines": f"{start}-{end}",
        "content": numbered,
        "html_url": data.get("html_url"),
    }
    if end < total:
        out["_more"] = True
        out["_hint"] = (
            f"Showing lines {start}-{end} of {total}. To read further, call "
            f"github_get again with params start_line={end + 1}."
        )
    return out


def _truncate(obj: Any) -> Any:
    """Keep the response under ``_MAX_RESPONSE_BYTES`` while preserving as
    much usable signal as possible.

    Strategy:
      * Lists → keep first N items, append a note that more were dropped.
      * Dicts with an ``items`` array → slice ``items``, keep totals.
      * Anything else → byte-clip with a preview envelope.
    """
    raw = json.dumps(obj, default=str)
    if len(raw) <= _MAX_RESPONSE_BYTES:
        return obj

    if isinstance(obj, list):
        # Find how many items fit, return a slice + note.
        kept: list[Any] = []
        running = 2  # for "[]"
        for it in obj:
            piece = json.dumps(it, default=str)
            if running + len(piece) + 2 > _MAX_RESPONSE_BYTES - 200:
                break
            kept.append(it)
            running += len(piece) + 2
        return {
            "_truncated": True,
            "_total_items": len(obj),
            "_kept_items": len(kept),
            "items": kept,
            "_hint": (
                f"Showing {len(kept)} of {len(obj)} items. Add filters / "
                "smaller per_page to drill down."
            ),
        }

    if isinstance(obj, dict) and isinstance(obj.get("items"), list):
        items = obj["items"]
        meta = {k: v for k, v in obj.items() if k != "items"}
        kept: list[Any] = []
        running = len(json.dumps(meta, default=str))
        for it in items:
            piece = json.dumps(it, default=str)
            if running + len(piece) + 2 > _MAX_RESPONSE_BYTES - 200:
                break
            kept.append(it)
            running += len(piece) + 2
        return {
            **meta,
            "items": kept,
            "_truncated": True,
            "_total_items": len(items),
            "_kept_items": len(kept),
            "_hint": (
                f"Showing {len(kept)} of {len(items)} items. Use filters or "
                "smaller per_page to narrow further."
            ),
        }

    return {
        "_truncated": True,
        "_original_size_bytes": len(raw),
        "_preview": raw[:_MAX_RESPONSE_BYTES],
        "_hint": (
            "Response was too large to include. Narrow your query (filters, "
            "per_page, or fetch a single resource)."
        ),
    }


# ──────────────────────────────────────────────────────────────────
# Extension hooks — set by app/agents/tools.py and app/rag at import time
# so chat_tools doesn't take a hard dependency on those (heavier) modules.
# Each factory takes the `install` dict and returns an async handler, or
# None if that capability is unavailable for this request.
# ──────────────────────────────────────────────────────────────────
WEB_SEARCH_HANDLER_FACTORY: Callable[[dict[str, Any]], ToolHandler | None] | None = None
SEMANTIC_SEARCH_HANDLER_FACTORY: (
    Callable[[dict[str, Any]], ToolHandler | None] | None
) = None
# Returns a dict of install-independent general-purpose handlers
# (python_exec, summarize, current_datetime). Set by app/agents/general_tools.
GENERAL_HANDLERS_FACTORY: (
    Callable[[dict[str, Any]], dict[str, ToolHandler]] | None
) = None


_TREE_RE = re.compile(r"^(/repos/[^/]+/[^/]+)/git/trees/([^/?]+)(.*)$")


async def _retry_tree_default_branch(
    install_id: int | None, path: str, params: dict[str, Any] | None
) -> Any | None:
    """If ``path`` is a ``git/trees/{branch}`` read that failed (wrong branch),
    look up the repo's real default branch and retry. Returns the result on
    success, or ``None`` if not applicable / still failing."""
    m = _TREE_RE.match(path)
    if not m:
        return None
    repo_base, branch, tail = m.group(1), m.group(2), m.group(3)
    if branch.upper() == "HEAD":
        return None  # HEAD already follows the default branch; nothing to fix
    try:
        meta = await gh_for(install_id).get(repo_base)
        default = (meta or {}).get("default_branch")
        if not default or default == branch:
            return None
        data = await gh_for(install_id).get(
            f"{repo_base}/git/trees/{default}{tail}", params=params or None
        )
        return _truncate(data)
    except Exception:
        return None


def build_tool_handlers(
    install: dict[str, Any], *, subset: set[str] | None = None
) -> dict[str, ToolHandler]:
    """Build the async tool handlers bound to one workspace.

    ``subset`` — if given, only handlers whose name is in the set are
    returned (sub-agents request a restricted toolset, e.g. a Code Analyst
    gets just ``github_get`` + ``semantic_search``). ``None`` ⇒ every
    available handler. The optional ``web_search`` / ``semantic_search``
    handlers are only included when their extension factory is registered
    and returns a handler (graceful degradation — the GitHub tools always
    work; the others appear only when their deps/keys/index exist).
    """
    install_id = install.get("install_id")
    org_login = install["account_login"]
    account_type = install.get("account_type", "Organization")
    mode = install.get("mode", "install")

    async def _github_get(path: str, params: dict[str, Any] | None = None) -> Any:
        if not _path_allowed(path):
            return {
                "error": "path_not_allowed",
                "message": (
                    f"The path {path!r} is not in the read-only allowlist. "
                    "Only GET requests to repos/orgs/users/search/installation "
                    "are permitted."
                ),
            }
        try:
            data = await gh_for(install_id).get(path, params=params or None)
        except Exception as exc:  # GitHubError or transport
            # Auto-recover a wrong-branch git/trees call (the model often guesses
            # main/master): retry against the repo's REAL default branch so a
            # tree read doesn't dead-end with "repo not found".
            retried = await _retry_tree_default_branch(install_id, path, params)
            if retried is not None:
                return retried
            return {"error": "github_error", "message": str(exc)}
        # A single-file read (/contents/ returns base64) — decode + page by lines
        # so the model can read a LARGE file in windows instead of a useless
        # byte-clip. Pass start_line / max_lines via `params` to page through.
        file_view = _maybe_file_window(data, params or {})
        if file_view is not None:
            return file_view
        # A LIST of fat objects (repos/commits/PRs/issues each carry ~80 fields,
        # ~5 KB) blows the truncation cap after ~1 item. Slim each object to the
        # fields that matter so the WHOLE list fits — this is why "list my repos"
        # returns all of them, not just the first one.
        data = _slim_rest_list(path, data)
        return _truncate(data)

    async def _github_search(
        type: str, query: str, per_page: int = 30
    ) -> Any:
        if type not in {"issues", "code", "repositories", "users", "commits"}:
            return {"error": "invalid_type", "message": f"unknown search type {type!r}"}
        path = f"/search/{type}"
        try:
            data = await gh_for(install_id).get(
                path, params={"q": query, "per_page": min(max(per_page, 1), 100)}
            )
        except Exception as exc:
            return {"error": "github_error", "message": str(exc)}
        # Slim the items so we don't blow the context window
        if isinstance(data, dict) and "items" in data:
            slim = {
                "total_count": data.get("total_count"),
                "items": [_slim_search_item(type, it) for it in data["items"]],
            }
            return _truncate(slim)
        return _truncate(data)

    async def _workspace_info() -> Any:
        info: dict[str, Any] = {
            "org_login": org_login,
            "account_type": account_type,
            "mode": mode,
            "scope_hint": (
                f"For search queries, scope with 'org:{org_login}' or "
                f"'repo:{org_login}/{{repo_name}}'."
            ),
        }
        try:
            limits = await gh_for(install_id).get("/rate_limit")
            core = (limits.get("rate") or {})
            info["rate_limit"] = {
                "remaining": core.get("remaining"),
                "limit": core.get("limit"),
                "reset_seconds": core.get("reset"),
            }
            search = (limits.get("resources") or {}).get("search") or {}
            info["search_rate_limit"] = {
                "remaining": search.get("remaining"),
                "limit": search.get("limit"),
            }
        except Exception:
            pass
        return info

    async def _github_graphql(
        query: str, variables: dict[str, Any] | None = None
    ) -> Any:
        # Guard against accidental mutations — read-only only.
        if "mutation" in query.lower().split("{", 1)[0]:
            return {"error": "mutations_not_allowed", "message": "read-only only"}
        client = gh_for(install_id)
        if not hasattr(client, "graphql"):
            return {
                "error": "graphql_unavailable",
                "message": "GraphQL requires an installed GitHub App (not public mode).",
            }
        try:
            data = await client.graphql(query, variables or None)
        except Exception as exc:
            return {"error": "github_error", "message": str(exc)}
        if isinstance(data, dict) and data.get("errors"):
            return {"error": "graphql_errors", "errors": data["errors"]}
        return _truncate(data)

    handlers: dict[str, ToolHandler] = {
        "github_get": _github_get,
        "github_search": _github_search,
        "workspace_info": _workspace_info,
    }
    # GraphQL needs an installation token — only offer it in install mode.
    if install_id is not None:
        handlers["github_graphql"] = _github_graphql

    # Optional capabilities — only registered when their factory yields a
    # handler for this install (key/dep/index present). Keeps the agent from
    # ever seeing a tool it can't use.
    if WEB_SEARCH_HANDLER_FACTORY is not None:
        web = WEB_SEARCH_HANDLER_FACTORY(install)
        if web is not None:
            handlers["web_search"] = web
    if SEMANTIC_SEARCH_HANDLER_FACTORY is not None:
        sem = SEMANTIC_SEARCH_HANDLER_FACTORY(install)
        if sem is not None:
            handlers["semantic_search"] = sem
    # General-purpose analysis tools (python_exec, summarize, current_datetime).
    if GENERAL_HANDLERS_FACTORY is not None:
        for name, handler in (GENERAL_HANDLERS_FACTORY(install) or {}).items():
            handlers[name] = handler

    if subset is not None:
        handlers = {k: v for k, v in handlers.items() if k in subset}
    return handlers


def available_tool_names(install: dict[str, Any]) -> set[str]:
    """Names of all handlers currently available for this workspace —
    used by app/agents/tools.py to decide which StructuredTools and which
    tool descriptions to advertise to the model."""
    return set(build_tool_handlers(install).keys())


def _result_preview(obj: Any) -> str:
    """Tiny human-readable preview of a tool result for the trace UI.

    The model receives the FULL object, not just this preview, so this
    doesn't affect agent reasoning — it only drives the collapsible
    "Used N tools" trace the frontend renders (one ChatToolCall per call).
    Lives here next to ``_truncate`` so both the legacy loop and the new
    LangGraph tracer (app/agents/trace.py) share one implementation.
    """
    if isinstance(obj, list):
        return f"{len(obj)} item(s)"
    if isinstance(obj, dict):
        if "error" in obj:
            return f"error: {obj['error']}"
        items = list(obj.items())[:2]
        parts = []
        for k, v in items:
            if isinstance(v, (str, int, float, bool)):
                parts.append(f"{k}={v}")
            elif isinstance(v, list):
                parts.append(f"{k}=[{len(v)}]")
            else:
                parts.append(k)
        return ", ".join(parts) if parts else f"keys: {list(obj.keys())[:3]}"
    return str(obj)[:80]


def _slim_repo(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": r.get("name"),
        "full_name": r.get("full_name"),
        "description": r.get("description"),
        "language": r.get("language"),
        "stars": r.get("stargazers_count"),
        "forks": r.get("forks_count"),
        "open_issues": r.get("open_issues_count"),
        "private": r.get("private"),
        "archived": r.get("archived"),
        "fork": r.get("fork"),
        "default_branch": r.get("default_branch"),
        "pushed_at": r.get("pushed_at"),       # last code push (use for "changed")
        "updated_at": r.get("updated_at"),     # any change (stars/desc/push)
        "created_at": r.get("created_at"),
        "url": r.get("html_url"),
        "homepage": r.get("homepage"),
    }


def _slim_commit(c: dict[str, Any]) -> dict[str, Any]:
    commit = c.get("commit") or {}
    author = commit.get("author") or {}
    gh_author = c.get("author") or {}
    return {
        "sha": (c.get("sha") or "")[:10],
        "message": (commit.get("message") or "").split("\n")[0][:140],
        "author": gh_author.get("login") or author.get("name"),
        "date": author.get("date"),
        "url": c.get("html_url"),
    }


def _slim_pr_or_issue(it: dict[str, Any]) -> dict[str, Any]:
    is_pr = "pull_request" in it or "head" in it
    return {
        "type": "pull_request" if is_pr else "issue",
        "number": it.get("number"),
        "title": it.get("title"),
        "state": it.get("state"),
        "draft": it.get("draft"),
        "user": (it.get("user") or {}).get("login"),
        "labels": [(lbl.get("name") if isinstance(lbl, dict) else lbl) for lbl in (it.get("labels") or [])][:6],
        "comments": it.get("comments"),
        "created_at": it.get("created_at"),
        "updated_at": it.get("updated_at"),
        "merged_at": it.get("merged_at"),
        "url": it.get("html_url"),
    }


def _slim_rest_list(path: str, data: Any) -> Any:
    """Slim a REST LIST response so the whole list fits the context budget.

    GitHub list objects (repos/commits/PRs/issues) carry ~80 fields each
    (~5 KB), so an un-slimmed list of 18 repos is ~100 KB and the truncation
    cap keeps only the first item — which is why the agent used to say "I can
    only see one repository". We map each object to the handful of fields that
    actually matter. Only applies to plain lists of dicts; anything else passes
    through untouched (``_truncate`` still guards the size).
    """
    # /installation/repositories wraps its list in {"total_count", "repositories"}
    # rather than returning a bare list, so it fell through every slimming rule
    # below and hit the 24 KB truncation cap — 170 KB collapsed into a single
    # `_preview` STRING. The model then guessed the repo count from a fragment
    # and got it wrong while sounding certain. Unwrap, slim, and keep the count.
    if isinstance(data, dict) and isinstance(data.get("repositories"), list):
        repos = data["repositories"]
        if repos and isinstance(repos[0], dict):
            slim = [_slim_repo(r) for r in repos]
            private = sum(1 for r in repos if r.get("private"))
            return {
                "total_count": data.get("total_count", len(repos)),
                "_returned": len(slim),
                "_private_count": private,
                "_public_count": len(repos) - private,
                "repository_selection": data.get("repository_selection"),
                "repositories": slim,
            }
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        return data
    p = path.lower()
    first = data[0]
    try:
        if "/repos" in p and "stargazers_count" in first:
            repos = [_slim_repo(r) for r in data]
            # The GitHub API already sorted these (default sort=pushed). Make the
            # ordering explicit + name the most-recent repo so the model doesn't
            # mis-rank a list it was handed correctly sorted.
            most_recent = max(
                repos, key=lambda r: r.get("pushed_at") or "", default=None
            )
            return {
                "_sorted_by": "pushed_at desc (most recent code push first)",
                "_count": len(repos),
                "_most_recently_pushed": most_recent.get("name") if most_recent else None,
                "repositories": repos,
            }
        if "/commits" in p and "commit" in first:
            return [_slim_commit(c) for c in data]
        if ("/pulls" in p or "/issues" in p) and "number" in first:
            return [_slim_pr_or_issue(it) for it in data]
        # Generic fat-list fallback: if items are large, keep common useful keys.
        if len(json.dumps(first, default=str)) > 1200:
            keep = (
                "id", "name", "full_name", "login", "number", "title", "sha",
                "state", "description", "html_url", "url", "created_at",
                "updated_at", "pushed_at",
            )
            return [{k: it.get(k) for k in keep if k in it} for it in data]
    except Exception:
        return data
    return data


def _slim_search_item(type: str, item: dict[str, Any]) -> dict[str, Any]:
    """Drop fields the model doesn't need for reasoning. Keeps context tight."""
    if type == "issues":
        user = (item.get("user") or {})
        repo_url = item.get("repository_url", "")
        repo = repo_url.rsplit("/", 1)[-1]
        is_pr = bool(item.get("pull_request"))
        return {
            "type": "pull_request" if is_pr else "issue",
            "number": item.get("number"),
            "title": item.get("title"),
            "state": item.get("state"),
            "merged": (item.get("pull_request") or {}).get("merged_at") is not None,
            "user": user.get("login"),
            "repo": repo,
            "url": item.get("html_url"),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
            "comments": item.get("comments"),
            "body_excerpt": (item.get("body") or "")[:300],
        }
    if type == "code":
        repo = (item.get("repository") or {}).get("full_name")
        return {
            "repo": repo,
            "path": item.get("path"),
            "name": item.get("name"),
            "url": item.get("html_url"),
        }
    if type == "repositories":
        return {
            "full_name": item.get("full_name"),
            "description": item.get("description"),
            "stars": item.get("stargazers_count"),
            "language": item.get("language"),
            "pushed_at": item.get("pushed_at"),
            "url": item.get("html_url"),
        }
    if type == "users":
        return {
            "login": item.get("login"),
            "type": item.get("type"),
            "url": item.get("html_url"),
        }
    return item
