"""Web Researcher sub-agent — gathers external context off GitHub.

Restricted toolset: ``web_search`` only. No delegate_* tools, so depth=1 holds
by construction. This sub-agent is only registered when ``web_search`` is
actually available for the workspace (key + dep present) — see
``app/agents/registry.py``.

Uses the CHEAP model (web role, ``use_fallback=True``): web research is a
high-volume, low-stakes summarisation task that doesn't warrant the strong
model. ``providers_module`` / ``tools_module`` are injected by the registry.
"""
from __future__ import annotations

from typing import Any

from app.agents.base import run_bounded_loop
from app.agents.budget import DelegationBudget
from app.agents.subagent_prompts import WEB_RESEARCHER_PROMPT
from app.agents.tracing import TraceCollector

NAME = "web_researcher"
DESCRIPTION = (
    "Delegate an EXTERNAL-RESEARCH question to the Web Researcher sub-agent. "
    "Use for information the GitHub API can't provide: library/framework docs, "
    "release notes and changelogs, CVEs and security advisories, best-practice "
    "guidance, or decoding error messages. It searches the public web and "
    "returns a concise finding with source-URL citations. Pass a single, "
    "focused research task."
)
TOOL_NAMES: set[str] = {"web_search"}
MODEL_ROLE = "web"
PROMPT = WEB_RESEARCHER_PROMPT


async def run(
    install: dict[str, Any],
    task: str,
    *,
    budget: DelegationBudget,
    trace: TraceCollector,
    providers_module: Any,
    tools_module: Any,
    focus_repo: str | None = None,  # accepted for a uniform signature; unused
) -> dict[str, Any]:
    """Run the Web Researcher over ``task`` and return ``{findings, ...}``.

    Builds the CHEAP model (web role with ``use_fallback=True``) and the
    web_search tool, then drives :func:`run_bounded_loop` with ``label=NAME``
    so its calls flatten into the shared trace as ``"web_researcher→web_search"``.
    """
    model = providers_module.model_for_spec(role=MODEL_ROLE, use_fallback=True)
    tools = tools_module.build_tools(install, names=TOOL_NAMES)

    findings = await run_bounded_loop(
        model=model,
        tools=tools,
        system_prompt=PROMPT,
        user_task=task,
        budget=budget,
        trace=trace,
        label=NAME,
    )
    return {
        "findings": findings,
        "citations": [],
        "tools_used": sorted(t.name for t in tools),
    }
