"""PR & Activity Analyst sub-agent — answers questions about PRs/issues/commits.

Restricted toolset: ``github_search`` (find PRs/issues/commits), ``github_get``
(authoritative details), and ``workspace_info`` (org + rate-limit budget). No
delegate_* tools, so depth=1 holds by construction.

Spec surface (NAME / DESCRIPTION / TOOL_NAMES / MODEL_ROLE / PROMPT) is consumed
by ``app/agents/registry.py``; :func:`run` builds the model + tools and drives
the bounded loop. ``providers_module`` / ``tools_module`` are injected by the
registry to avoid hard-importing the parallel-built siblings.
"""
from __future__ import annotations

from typing import Any

from app.agents.base import run_bounded_loop
from app.agents.budget import DelegationBudget
from app.agents.subagent_prompts import PR_ANALYST_PROMPT, bound_tools_block
from app.agents.tracing import TraceCollector

NAME = "pr_activity_analyst"
DESCRIPTION = (
    "Delegate a PR / ACTIVITY question to the PR & Activity Analyst sub-agent. "
    "Use for: pull requests and reviews, issues, commits, contributor activity, "
    "team velocity, and what's open / stuck / recently merged. It searches and "
    "reads GitHub via the org's auth and returns a concise factual finding with "
    "concrete numbers and PR/issue/commit citations. Pass a single, "
    "well-scoped task; optionally focus_repo to limit it to one repository."
)
TOOL_NAMES: set[str] = {
    "github_search",
    "github_get",
    "workspace_info",
    "python_exec",
    "current_datetime",
}
MODEL_ROLE = "analyst"
PROMPT = PR_ANALYST_PROMPT


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
    """Run the PR/Activity Analyst over ``task`` and return ``{findings, ...}``.

    Builds a STRONG model (analyst role) and the restricted toolset, then
    drives :func:`run_bounded_loop` with ``label=NAME`` so its tool calls
    flatten into the shared trace as ``"pr_activity_analyst→{tool}"``.
    """
    model = providers_module.model_for_spec(role=MODEL_ROLE)
    tools = tools_module.build_tools(install, names=TOOL_NAMES)
    # The prompt describes a superset; state what is really bound.
    system_prompt = PROMPT + bound_tools_block({t.name for t in tools})

    # Tell the sub-agent the owner/org explicitly — its own system prompt does
    # not carry the ACTIVE WORKSPACE block, so without this it builds wrong
    # paths (missing the owner) and 404s.
    owner = install.get("account_login_display") or install.get("account_login", "")
    ctx = (
        f"WORKSPACE: the GitHub owner/org for ALL paths is `{owner}`. "
        f"Always use /repos/{owner}/{{repo}}/... and scope searches with "
        f"org:{owner} or repo:{owner}/{{repo}} — never omit the owner."
    )
    repo_line = f"\nFocus only on the repository: {focus_repo}." if focus_repo else ""
    user_task = f"{ctx}\n\nTASK: {task}{repo_line}"
    findings = await run_bounded_loop(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
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
