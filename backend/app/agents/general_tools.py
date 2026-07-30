"""General-purpose agent tools — make the agent able to handle ANY query.

The GitHub/RAG/web tools let the agent *fetch* data; these let it *reason over,
compute, and transform* that data the way a human analyst would. They are what
turn "calculate the average PR cycle time", "summarize these 200 commits", or
"what's the date 30 days ago" from impossible into trivial.

Tools added here (registered onto chat_tools' generic registry):
  * ``python_exec``      — run Python for calculation / data analysis / charts.
  * ``summarize``        — recursive LLM compression of long content.
  * ``current_datetime`` — real wall-clock time so relative windows resolve.

``python_exec`` runs in a restricted sandbox (curated builtins, no filesystem /
network / process access, wall-clock timeout in a worker thread). It's meant for
analysis/computation on data the agent already gathered — not arbitrary I/O.
"""
from __future__ import annotations

import asyncio
import builtins as _builtins
import io
import json as _json_mod
import math
import re as _re_mod
import statistics
from collections import Counter as _Counter
from collections import defaultdict as _defaultdict
from datetime import date as _date
from datetime import datetime, timedelta, timezone
from datetime import datetime as _dt
from datetime import timedelta as _td
from typing import Any

# Tools are registered onto the existing generic registry so build_tool_handlers
# can hand them out (and sub-agents can request them by name).
from app.services import chat_tools

# ──────────────────────────────────────────────────────────────────
# python_exec — restricted Python execution for analysis/computation.
# ──────────────────────────────────────────────────────────────────
_PYTHON_TIMEOUT_S = 8.0

# A curated, read-only builtin set. No open/exec/eval/__import__/input/etc.
_SAFE_BUILTINS = {
    name: getattr(_builtins, name)
    for name in (
        "abs", "all", "any", "ascii", "bin", "bool", "bytearray", "bytes",
        "chr", "complex", "dict", "divmod", "enumerate", "filter", "float",
        "format", "frozenset", "hex", "int", "isinstance", "issubclass",
        "iter", "len", "list", "map", "max", "min", "next", "oct", "ord",
        "pow", "print", "range", "repr", "reversed", "round", "set", "slice",
        "sorted", "str", "sum", "tuple", "type", "zip",
    )
    if hasattr(_builtins, name)
}

# Modules/names the sandbox may use — analysis staples only, all safe (no I/O,
# no process, no network). Pre-injected as globals AND importable (see
# ``_safe_import``) so the model can write `statistics.mean(...)` with or
# without an `import` line.
_SAFE_MODULES: dict[str, Any] = {
    "math": math,
    "statistics": statistics,
    "json": _json_mod,
    "re": _re_mod,
    "datetime": _dt,
    "date": _date,
    "timedelta": _td,
    "Counter": _Counter,
    "defaultdict": _defaultdict,
}

# Top-level module names the sandbox's `import` is allowed to resolve.
_IMPORTABLE = {"math", "statistics", "json", "re", "datetime", "collections"}


def _safe_import(name: str, *args: Any, **kwargs: Any) -> Any:
    """A restricted __import__ that only resolves the analysis-safe modules."""
    root = name.split(".")[0]
    if root not in _IMPORTABLE:
        raise ImportError(
            f"import of {name!r} is not allowed in python_exec "
            f"(safe modules: {sorted(_IMPORTABLE)})"
        )
    import importlib

    return importlib.import_module(name)


def _run_python_sync(code: str) -> dict[str, Any]:
    """Execute ``code`` with restricted builtins, capturing stdout + ``result``.

    Convention: if the snippet assigns a variable named ``result``, we return
    its repr; otherwise we return captured stdout. Errors are returned as a
    structured dict so the model can recover, never raised.
    """
    import json as _json

    buf = io.StringIO()
    sandbox_globals: dict[str, Any] = {
        "__builtins__": _SAFE_BUILTINS,
        **_SAFE_MODULES,
    }
    sandbox_locals: dict[str, Any] = {}

    def _capturing_print(*args: Any, **kw: Any) -> None:
        kw.setdefault("file", buf)
        _builtins.print(*args, **kw)

    sandbox_globals["__builtins__"] = {
        **_SAFE_BUILTINS,
        "print": _capturing_print,
        "__import__": _safe_import,  # only resolves analysis-safe modules
    }

    try:
        compiled = compile(code, "<python_exec>", "exec")
        exec(compiled, sandbox_globals, sandbox_locals)  # noqa: S102 (sandboxed)
    except Exception as exc:  # surface as recoverable data, not an exception
        return {
            "error": f"{type(exc).__name__}: {exc}",
            "stdout": buf.getvalue()[:4000],
            "hint": "Fix the code and try again. Only math/statistics modules "
            "and safe builtins are available; no file/network/import access.",
        }

    out: dict[str, Any] = {"stdout": buf.getvalue()[:6000]}
    if "result" in sandbox_locals:
        try:
            val = sandbox_locals["result"]
            # Prefer JSON for structured values; fall back to repr.
            out["result"] = _json.loads(_json.dumps(val, default=repr))
        except Exception:
            out["result"] = repr(sandbox_locals["result"])[:6000]
    return out


async def _python_exec(code: str) -> Any:
    """Run a Python snippet in the restricted sandbox with a hard timeout."""
    if not isinstance(code, str) or not code.strip():
        return {"error": "empty_code", "hint": "Pass a Python snippet as `code`."}
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_run_python_sync, code), timeout=_PYTHON_TIMEOUT_S
        )
    except TimeoutError:
        return {
            "error": "timeout",
            "hint": f"Code exceeded {_PYTHON_TIMEOUT_S}s. Avoid heavy loops.",
        }


# ──────────────────────────────────────────────────────────────────
# current_datetime — real time so relative windows resolve correctly.
# ──────────────────────────────────────────────────────────────────
async def _current_datetime() -> Any:
    now = datetime.now(timezone.utc)
    return {
        "utc_now": now.isoformat(),
        "date": now.date().isoformat(),
        "weekday": now.strftime("%A"),
        "since_7d": (now - timedelta(days=7)).date().isoformat(),
        "since_30d": (now - timedelta(days=30)).date().isoformat(),
        "since_90d": (now - timedelta(days=90)).date().isoformat(),
        "hint": "Use these ISO dates with GitHub's `since=`/`created:>=` filters "
        "for 'this week' (7d), 'this month' (30d), 'this quarter' (90d).",
    }


# ──────────────────────────────────────────────────────────────────
# summarize — recursive LLM compression of long content.
# ──────────────────────────────────────────────────────────────────
async def _summarize(text: str, instructions: str = "") -> Any:
    """Compress long content via a cheap model call. Chunks + reduces if huge."""
    if not isinstance(text, str) or not text.strip():
        return {"error": "empty_text"}

    try:
        from app.agents.providers import enabled_providers, model_for_spec
    except Exception as exc:
        return {"error": "summarize_unavailable", "message": str(exc)}

    if not enabled_providers():
        return {"error": "no_provider"}

    instr = instructions.strip() or "Summarize the key points concisely."

    async def _one(chunk: str) -> str:
        model = model_for_spec(role="web", use_fallback=True)  # cheap model
        prompt = (
            f"{instr}\n\nContent to summarize:\n{chunk}\n\n"
            "Return only the summary, no preamble."
        )
        from langchain_core.messages import HumanMessage

        resp = await model.ainvoke([HumanMessage(content=prompt)])
        content = getattr(resp, "content", "")
        if isinstance(content, list):  # provider block-list form
            content = "".join(
                b.get("text", "") for b in content if isinstance(b, dict)
            )
        return str(content).strip()

    # Map-reduce when the input is large (keep each chunk well under context).
    CHUNK = 12_000
    if len(text) <= CHUNK:
        try:
            return {"summary": await _one(text)}
        except Exception as exc:
            return {"error": "summarize_failed", "message": str(exc)}

    chunks = [text[i : i + CHUNK] for i in range(0, len(text), CHUNK)]
    try:
        partials = [await _one(c) for c in chunks[:8]]  # cap fan-out
        combined = "\n\n".join(partials)
        final = await _one(combined) if len(combined) > CHUNK else combined
        return {"summary": final, "chunks_summarized": len(partials)}
    except Exception as exc:
        return {"error": "summarize_failed", "message": str(exc)}


# ──────────────────────────────────────────────────────────────────
# remember — write a durable fact to the user's cross-chat memory.
# Bound per-request to (user_id, org) carried on the install dict.
# ──────────────────────────────────────────────────────────────────
def _make_remember(install: dict[str, Any]) -> Any:
    user_id = install.get("_user_id")
    org = install.get("account_login")

    async def remember(text: str, category: str = "fact") -> Any:
        if user_id is None or not org:
            return {"error": "memory_unavailable", "message": "no user context"}
        try:
            from app.services.user_memory import add_memory

            entry = await add_memory(user_id, org, text, category=category)
            return {"saved": True, "text": entry.get("text", text)}
        except ValueError as exc:
            return {"error": str(exc)}
        except Exception as exc:
            return {"error": "remember_failed", "message": str(exc)}

    return remember


# ──────────────────────────────────────────────────────────────────
# Registration — append handlers onto the generic registry's factory hook.
# ──────────────────────────────────────────────────────────────────
def _general_handlers_factory(install: dict[str, Any]) -> dict[str, Any]:
    """Return the general-purpose handlers (some bound to the request)."""
    handlers: dict[str, Any] = {
        "python_exec": _python_exec,
        "current_datetime": _current_datetime,
        "summarize": _summarize,
    }
    # remember is only offered when we have a user context to scope it to.
    if install.get("_user_id") is not None:
        handlers["remember"] = _make_remember(install)
    return handlers


# chat_tools.build_tool_handlers consults this to add the general tools. They
# are install-independent, so the factory ignores `install`.
chat_tools.GENERAL_HANDLERS_FACTORY = _general_handlers_factory
