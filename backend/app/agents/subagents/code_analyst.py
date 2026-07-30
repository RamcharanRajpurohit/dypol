"""Code Analyst sub-agent — answers questions about the code itself.

Restricted toolset: ``semantic_search`` (discover relevant files by meaning)
and ``github_get`` (read the authoritative current content). It has NO
delegate_* tools, so it structurally cannot sub-delegate (depth=1 by
construction).

This module exposes a small *spec* surface (NAME / DESCRIPTION / TOOL_NAMES /
MODEL_ROLE / PROMPT) consumed by ``app/agents/registry.py``, plus an async
:func:`run` that builds the model + tools and drives the bounded loop. The
``providers_module`` and ``tools_module`` are passed IN by the registry so this
file never hard-imports the (parallel-built) sibling modules at import time.
"""
from __future__ import annotations

from typing import Any

from app.agents.base import run_bounded_loop
from app.agents.budget import DelegationBudget
from app.agents.subagent_prompts import CODE_ANALYST_PROMPT
from app.agents.tracing import TraceCollector

NAME = "code_analyst"
DESCRIPTION = (
    "Delegate a CODE question to the Code Analyst sub-agent. Use for: where a "
    "feature is implemented, how a module/function works, what a file does, "
    "cross-file usage, or locating code by meaning. It runs semantic search "
    "over the indexed codebase and reads authoritative file contents via the "
    "GitHub API, then returns a concise grounded finding with file/path "
    "citations. Pass a single, sharply-scoped task; optionally focus_repo to "
    "limit it to one repository."
)
# semantic_search is optional (only present when RAG is indexed); github_get
# always exists, so this sub-agent is always runnable.
TOOL_NAMES: set[str] = {
    "semantic_search",
    "github_get",
    "github_graphql",
    "python_exec",
}
MODEL_ROLE = "analyst"
PROMPT = CODE_ANALYST_PROMPT


async def run(
    install: dict[str, Any],
    task: str,
    *,
    budget: DelegationBudget,
    trace: TraceCollector,
    providers_module: Any,
    tools_module: Any,
    focus_repo: str | None = None,
) -> dict[str, Any]:
    """Run the Code Analyst over ``task`` and return ``{findings, citations}``.

    Builds a STRONG model (analyst role — defaults to the first-enabled
    provider's primary model) and the restricted toolset, then drives
    :func:`run_bounded_loop` with ``label=NAME`` so the analyst's own tool
    calls flatten into the shared trace as ``"code_analyst→{tool}"``.
    """
    model = providers_module.model_for_spec(role=MODEL_ROLE)
    tools = tools_module.build_tools(install, names=TOOL_NAMES)

    # The sub-agent has its own system prompt and does NOT see the orchestrator's
    # ACTIVE WORKSPACE block — so we MUST tell it the owner/org explicitly, or it
    # builds wrong paths like /repos/{repo}/contents (missing the owner) and 404s.
    owner = install.get("account_login_display") or install.get("account_login", "")
    ctx = (
        f"WORKSPACE: the GitHub owner/org for ALL paths is `{owner}`. "
        f"Always use /repos/{owner}/{{repo}}/... — never omit the owner. "
        "To read a repo's docs, github_get('/repos/{owner}/{repo}/readme'); "
        "to list files, github_get('/repos/{owner}/{repo}/contents'); to read a "
        "file, github_get('/repos/{owner}/{repo}/contents/{path}')."
    )
    repo_line = f"\nFocus only on the repository: {focus_repo}." if focus_repo else ""
    user_task = f"{ctx}\n\nTASK: {task}{repo_line}"
    findings = await run_bounded_loop(
        model=model,
        tools=tools,
        system_prompt=PROMPT,
        user_task=user_task,
        budget=budget,
        trace=trace,
        label=NAME,
    )
    return {
        "findings": findings,
        "citations": [],
        "tools_used": sorted(t.name for t in tools),
    }
