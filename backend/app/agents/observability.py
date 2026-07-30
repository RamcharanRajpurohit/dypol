"""Observability — Langfuse tracing for the LangGraph agent (optional).

The research's #1 highest-leverage gap: "you can't improve, cost-control, or
safely ship an agent you cannot measure." Langfuse instruments the graph via a
LangChain ``CallbackHandler`` passed in the run ``config={"callbacks": [...]}``,
producing a trace of spans for every step (each LLM call + tool call) with token
usage, latency, and cost — plus online LLM-as-judge and offline regression evals
in the Langfuse UI.

Fully OPTIONAL: with no Langfuse keys set, ``get_callbacks()`` returns ``[]`` and
the agent runs exactly as before. Heavy imports are lazy so a missing dep can't
break boot.
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_settings

log = logging.getLogger("dypol.observability")

_handler: Any | None = None
_probed = False


def is_enabled() -> bool:
    s = get_settings()
    return bool(s.langfuse_public_key and s.langfuse_secret_key)


def _get_handler() -> Any | None:
    """Lazily build a process-wide Langfuse CallbackHandler, or None."""
    global _handler, _probed
    if _probed:
        return _handler
    _probed = True
    if not is_enabled():
        return None
    s = get_settings()
    try:
        import os

        # The langfuse SDK reads these from the environment.
        os.environ.setdefault("LANGFUSE_PUBLIC_KEY", s.langfuse_public_key or "")
        os.environ.setdefault("LANGFUSE_SECRET_KEY", s.langfuse_secret_key or "")
        os.environ.setdefault("LANGFUSE_HOST", s.langfuse_host)
        from langfuse.langchain import CallbackHandler

        _handler = CallbackHandler()
        log.info("Langfuse tracing enabled (host=%s)", s.langfuse_host)
    except Exception as exc:  # never let observability break the agent
        log.warning("Langfuse disabled: %s", exc)
        _handler = None
    return _handler


def get_callbacks(
    *, user_id: int | None = None, org: str | None = None, session_id: str | None = None
) -> list[Any]:
    """Return the list of LangChain callbacks for a run (empty if disabled).

    Pass this into the graph as ``config={"callbacks": get_callbacks(...)}``.
    The user/org/session are attached as trace metadata for per-tenant filtering
    in the Langfuse UI.
    """
    handler = _get_handler()
    return [handler] if handler is not None else []


def run_metadata(
    *, user_id: int | None = None, org: str | None = None, session_id: str | None = None
) -> dict[str, Any]:
    """LangGraph run metadata/tags merged into the trace for filtering."""
    md: dict[str, Any] = {}
    if user_id is not None:
        md["langfuse_user_id"] = str(user_id)
    if session_id:
        md["langfuse_session_id"] = session_id
    if org:
        md["org"] = org
    return md
