"""registry — builds the ``delegate_*`` sub-agent tools (agent-as-tool).

The orchestrator (``app/agents/graph.py``) calls :func:`build_delegate_tools`
to obtain a list of LangChain :class:`StructuredTool` objects — one per
available specialist sub-agent — which it hands to the top-level model exactly
like any other tool. When the model calls e.g. ``delegate_code_analyst(task=…)``
the wrapped coroutine:

  1. checks the shared :class:`DelegationBudget` (breadth / dedupe) and returns
     a recoverable ``{"error": ...}`` dict if exhausted — never raises;
  2. records the visible ``delegate_{name}`` row into the shared flat trace;
  3. runs the sub-agent's bounded loop, whose own tool calls are recorded by
     ``run_bounded_loop`` with ``label=spec.NAME`` so they flatten into the
     same trace as ``"{name}→{tool}"``;
  4. returns ``{"findings", "citations"}`` back to the orchestrator.

DEPTH SAFETY: sub-agents receive a *restricted* tool subset that never
includes any ``delegate_*`` tool, so they structurally cannot sub-delegate
(``max_depth=1`` enforced by construction, not by a runtime check).

These are PRODUCT RUNTIME agents (one set spawned per end-user question to
answer about a GitHub org), distinct from the ``.claude/agents`` *dev-time*
subagents used by Claude Code while building this repo. They deliberately
mirror that concept (name, description, tool allowlist, model role, prompt) but
execute inside this FastAPI backend.

This module is side-effect-free at import: the heavier ``app.agents.providers``
and ``app.agents.tools`` modules (built in parallel) are imported LAZILY inside
the delegate coroutine, so importing ``registry`` never drags them in.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.agents.budget import DelegationBudget
from app.agents.subagents import code_analyst, pr_activity_analyst, web_researcher
from app.agents.tracing import TraceCollector

# The specialist sub-agent spec modules, in routing-priority order. Each module
# exposes: NAME, DESCRIPTION, TOOL_NAMES, MODEL_ROLE, PROMPT, async run(...).
SUBAGENTS: list[Any] = [code_analyst, pr_activity_analyst, web_researcher]


# ── delegate-tool argument schemas ───────────────────────────────────
class _DelegateTask(BaseModel):
    """Args for sub-agents that operate org-wide (e.g. web_researcher)."""

    task: str = Field(
        ...,
        description=(
            "A single, sharply-scoped task for the sub-agent to investigate. "
            "Be specific — it cannot ask you clarifying questions."
        ),
    )


class _DelegateRepoTask(BaseModel):
    """Args for repo-aware sub-agents (code_analyst / pr_activity_analyst)."""

    task: str = Field(
        ...,
        description=(
            "A single, sharply-scoped task for the sub-agent to investigate. "
            "Be specific — it cannot ask you clarifying questions."
        ),
    )
    focus_repo: str | None = Field(
        None,
        description=(
            "Optional: limit the sub-agent to one repository "
            "(name or owner/name) when the question is about a single repo."
        ),
    )


# Which spec modules accept a focus_repo (get the repo-aware schema).
_REPO_AWARE = {code_analyst.NAME, pr_activity_analyst.NAME}


def _is_available(spec: Any, available: set[str]) -> bool:
    """Whether ``spec`` can run for this workspace.

    A sub-agent is available iff at least one of its tools is available. In
    practice:
      * code_analyst — always (github_get is always present; semantic_search
        is a bonus when RAG is indexed).
      * pr_activity_analyst — always (all three GitHub tools are core).
      * web_researcher — only when web_search is available (key + dep present).
    """
    return bool(spec.TOOL_NAMES & available)


def build_delegate_tools(
    install: dict[str, Any],
    *,
    budget: DelegationBudget,
    trace: TraceCollector,
):
    """Build the ``delegate_*`` StructuredTools for one workspace + turn.

    Returns a (possibly empty) list of :class:`StructuredTool`. Side-effect
    free except for the lazy imports performed *inside* each tool's coroutine.
    The same ``budget`` and ``trace`` instances must be the ones the
    orchestrator uses, so nested calls share one flat trace and one budget.
    """
    # Lazy imports — these are light (chat_tools) but kept lazy for symmetry and
    # to avoid any import-order coupling with the parallel-built tools module.
    from langchain_core.tools import StructuredTool

    from app.services.chat_tools import _result_preview, available_tool_names

    available = available_tool_names(install)

    tools: list[Any] = []
    for spec in SUBAGENTS:
        if not _is_available(spec, available):
            continue

        tool = _make_delegate_tool(
            spec,
            install=install,
            budget=budget,
            trace=trace,
            structured_tool_cls=StructuredTool,
            result_preview=_result_preview,
        )
        tools.append(tool)
    return tools


def _make_delegate_tool(
    spec: Any,
    *,
    install: dict[str, Any],
    budget: DelegationBudget,
    trace: TraceCollector,
    structured_tool_cls: Any,
    result_preview: Any,
):
    """Construct one ``delegate_{spec.NAME}`` StructuredTool bound to ``spec``."""
    name = spec.NAME
    tool_name = f"delegate_{name}"
    args_schema = _DelegateRepoTask if name in _REPO_AWARE else _DelegateTask

    async def _delegate(task: str, focus_repo: str | None = None) -> dict[str, Any]:
        # Dedupe / breadth key: the sub-agent + its task text.
        task_key = f"{name}:{task.strip()}"
        if not budget.can_delegate(task_key):
            err = {
                "error": "delegation_budget_exhausted",
                "hint": (
                    "No more delegations are allowed for this turn (or this "
                    "exact task was already delegated). Answer with the data "
                    "already gathered."
                ),
            }
            # Make the refusal visible in the trace so the UI shows the attempt.
            trace.record(tool_name, {"task": task}, "error: delegation_budget_exhausted", 0)
            return err

        # Visible delegate row (the parent-level call). The sub-agent's own
        # internal tool calls are recorded separately with label=spec.NAME.
        trace.record(
            tool_name,
            {"task": task, **({"focus_repo": focus_repo} if focus_repo else {})},
            f"delegating to {name}",
            0,
        )
        budget.note_delegation(task_key)

        # Lazy import of the parallel-built sibling modules — only needed at
        # call time, never at import time.
        from app.agents import providers as providers_module
        from app.agents import tools as tools_module

        run_kwargs: dict[str, Any] = {
            "budget": budget,
            "trace": trace,
            "providers_module": providers_module,
            "tools_module": tools_module,
        }
        if name in _REPO_AWARE:
            run_kwargs["focus_repo"] = focus_repo

        try:
            result = await spec.run(install, task, **run_kwargs)
        except Exception as exc:  # a sub-agent failure must stay recoverable
            return {
                "error": "subagent_failed",
                "message": str(exc),
                "hint": "Answer using the data already gathered, or try a different approach.",
            }

        return {
            "findings": result.get("findings", ""),
            "citations": result.get("citations", []),
        }

    return structured_tool_cls.from_function(
        coroutine=_delegate,
        name=tool_name,
        description=spec.DESCRIPTION,
        args_schema=args_schema,
    )
