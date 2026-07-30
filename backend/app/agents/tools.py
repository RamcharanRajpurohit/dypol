"""Tools — LangChain StructuredTool wrappers over the existing handlers.

The agent's tools are the *same* async handlers ``services/chat_tools`` builds
(github_get / github_search / workspace_info, plus optional web_search and
semantic_search). Here we wrap each into a ``StructuredTool`` with a typed
pydantic arg schema and the shared ``TOOL_DESCRIPTIONS`` so every provider
sees identical guidance.

This module also REGISTERS the web-search extension factory on
``chat_tools.WEB_SEARCH_HANDLER_FACTORY`` at import time, so ``chat_tools``
gains a ``web_search`` handler without taking a hard dependency on the
(heavier, optional) search backends. The factory lazy-imports its backend and
returns ``None`` when no backend is importable — graceful degradation.
"""
from __future__ import annotations

import asyncio
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.services import chat_tools
from app.services.chat_tools import (
    TOOL_DESCRIPTIONS,
    _truncate,
    build_tool_handlers,
)


# ──────────────────────────────────────────────────────────────────
# Pydantic arg schemas — one per tool. Kept loose where providers are
# fussy: Gemini rejects deeply-typed free-form objects, so ``params`` is an
# open ``dict[str, Any] | None`` rather than a nested model.
# ──────────────────────────────────────────────────────────────────
class GithubGetArgs(BaseModel):
    path: str = Field(
        ...,
        description="API path starting with /. e.g. '/repos/vercel/next.js'",
    )
    params: dict[str, Any] | None = Field(
        default=None,
        description=(
            'Optional query params, e.g. {"per_page": 50, "state": "open"}. '
            "Strings/numbers only."
        ),
    )


class GithubSearchArgs(BaseModel):
    type: Literal["issues", "code", "repositories", "users", "commits"] = Field(
        ..., description="Which /search/{type} endpoint to hit."
    )
    query: str = Field(
        ...,
        description=(
            "GitHub search syntax. ALWAYS scope with org:{login} or "
            "repo:{owner}/{repo} for the active workspace."
        ),
    )
    per_page: int = Field(30, description="1-100, default 30.")


class WorkspaceInfoArgs(BaseModel):
    pass


class GithubGraphqlArgs(BaseModel):
    query: str = Field(..., description="A read-only GitHub GraphQL v4 query.")
    variables: dict[str, Any] | None = Field(
        default=None, description="Optional GraphQL variables object."
    )


class WebSearchArgs(BaseModel):
    query: str = Field(..., description="What to search the public web for.")
    max_results: int = Field(5, description="How many results to return (1-10).")


class PythonExecArgs(BaseModel):
    code: str = Field(
        ...,
        description=(
            "Python to run for calculation/analysis. Use math/statistics + safe "
            "builtins (no file/network/import). Assign the answer to `result` or "
            "print() it. e.g. `result = statistics.mean([3,5,8,2])`."
        ),
    )


class SummarizeArgs(BaseModel):
    text: str = Field(..., description="The long content to compress.")
    instructions: str = Field(
        "", description="Optional: what to focus the summary on."
    )


class CurrentDatetimeArgs(BaseModel):
    pass


class RememberArgs(BaseModel):
    text: str = Field(
        ..., description="The durable fact/preference to remember about the user."
    )
    category: str = Field(
        "fact", description="One of: fact | preference | context."
    )


# Map handler name → (arg schema | None). ``None`` ⇒ let StructuredTool infer
# from the coroutine signature (used for semantic_search, whose schema lives in
# the RAG layer).
_ARG_SCHEMAS: dict[str, type[BaseModel] | None] = {
    "github_get": GithubGetArgs,
    "github_search": GithubSearchArgs,
    "workspace_info": WorkspaceInfoArgs,
    "github_graphql": GithubGraphqlArgs,
    "web_search": WebSearchArgs,
    "semantic_search": None,
    "python_exec": PythonExecArgs,
    "summarize": SummarizeArgs,
    "current_datetime": CurrentDatetimeArgs,
    "remember": RememberArgs,
}


def build_tools(
    install: dict[str, Any],
    *,
    names: set[str] | None = None,
    extra_tools: list[Any] | None = None,
) -> list[Any]:
    """Build the LangChain ``StructuredTool`` list for one workspace.

    ``names`` restricts to a subset (sub-agents request a narrow toolset).
    ``extra_tools`` (the delegate_* sub-agent tools) are appended as-is.
    Only handlers actually present for this install are wrapped, so the model
    never sees a tool it can't use.

    ``workspace_info`` stays available (its small result never errors), but the
    system prompt no longer tells the model to "always start" with it — that
    instruction caused some models (Gemini) to call it first and then stall.
    Everything it returns is already in the system prompt, so the model rarely
    needs it now.
    """
    from langchain_core.tools import StructuredTool

    handlers = build_tool_handlers(install, subset=names)
    tools: list[Any] = []
    for name, handler in handlers.items():
        schema = _ARG_SCHEMAS.get(name)
        tools.append(
            StructuredTool.from_function(
                coroutine=handler,
                name=name,
                description=TOOL_DESCRIPTIONS.get(name, name),
                args_schema=schema,
            )
        )
    if extra_tools:
        tools.extend(extra_tools)
    return tools


# ──────────────────────────────────────────────────────────────────
# Web-search extension factory.
#
# Returns an async ``web_search`` handler when WEB_SEARCH_ENABLED, using
# Tavily (keyed, better) when TAVILY_API_KEY is set, else DuckDuckGo (no key).
# Returns None when disabled or when neither backend is importable — in which
# case chat_tools simply doesn't register the tool.
# ──────────────────────────────────────────────────────────────────
def _normalize_results(raw: Any) -> list[dict[str, Any]]:
    """Coerce a backend's results into ``list[{title, url, content}]``."""
    items: list[Any]
    if isinstance(raw, dict):
        items = raw.get("results") or raw.get("items") or []
    elif isinstance(raw, list):
        items = raw
    elif isinstance(raw, str):
        # Some community tools return a single formatted string.
        return [{"title": "", "url": "", "content": raw}]
    else:
        items = []

    out: list[dict[str, Any]] = []
    for it in items:
        if isinstance(it, dict):
            out.append(
                {
                    "title": it.get("title") or it.get("name") or "",
                    "url": it.get("url") or it.get("link") or it.get("href") or "",
                    "content": (
                        it.get("content")
                        or it.get("snippet")
                        or it.get("body")
                        or it.get("description")
                        or ""
                    ),
                }
            )
        else:
            out.append({"title": "", "url": "", "content": str(it)})
    return out


def _web_search_factory(install: dict[str, Any]) -> Any:
    """Build a ``web_search`` async handler, or return None if unavailable."""
    s = get_settings()
    if not s.web_search_enabled:
        return None

    use_tavily = bool(s.tavily_api_key)

    # Probe importability up front so we can decline (return None) cleanly
    # rather than registering a tool that always errors.
    backend: str | None = None
    if use_tavily:
        try:
            import langchain_tavily  # noqa: F401

            backend = "tavily"
        except Exception:
            backend = None
    if backend is None:
        try:
            import langchain_community.tools  # noqa: F401

            backend = "duckduckgo"
        except Exception:
            backend = None
    if backend is None:
        return None

    async def web_search(
        query: str, max_results: int = s.web_search_max_results
    ) -> Any:
        k = min(max(int(max_results), 1), 10)
        try:
            if backend == "tavily":
                from langchain_tavily import TavilySearch

                search = TavilySearch(
                    max_results=k, tavily_api_key=s.tavily_api_key
                )
                raw = await search.ainvoke({"query": query})
            else:
                from langchain_community.tools import DuckDuckGoSearchResults

                search = DuckDuckGoSearchResults(
                    num_results=k, output_format="list"
                )
                try:
                    raw = await search.ainvoke(query)
                except NotImplementedError:
                    # Some community tools are sync-only — run off-loop.
                    raw = await asyncio.to_thread(search.invoke, query)
            return _truncate(_normalize_results(raw))
        except Exception as exc:
            return {
                "error": "web_search_unavailable",
                "message": str(exc),
            }

    return web_search


# Register at import — chat_tools.build_tool_handlers will consult this.
chat_tools.WEB_SEARCH_HANDLER_FACTORY = _web_search_factory

# Importing general_tools registers the python_exec / summarize /
# current_datetime handlers onto chat_tools.GENERAL_HANDLERS_FACTORY. Done here
# so that the single startup import of app.agents.tools wires every base tool.
from app.agents import general_tools  # noqa: E402,F401
