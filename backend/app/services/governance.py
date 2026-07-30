"""Governance — cost controls, circuit breaker, and audit logging.

Production/MNC-grade controls the research flagged as gaps:

  * Per-(user, org) DAILY token budget cap (cost control) — Mongo-backed counter
    with a UTC-day key; refuses new turns once the ceiling is hit.
  * Circuit breaker — after N consecutive provider failures, short-circuit for a
    cooldown instead of hammering a down provider.
  * Structured AUDIT LOG — one record per turn (actor, org, session, tools used,
    model, token estimate, latency) with secret/PII REDACTION so the audit trail
    can't itself leak credentials (GDPR/PCI/SOC2 requirement).

All controls are app-enforced and fail OPEN (an internal error here never blocks
a user's chat) except the budget cap, which fails closed only when explicitly
exceeded.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

from app.core.config import get_settings
from app.core.db import get_db

log = logging.getLogger("dypol.governance")


# ──────────────────────────────────────────────────────────────────
# Secret / PII redaction — applied before anything is written to the audit log.
# ──────────────────────────────────────────────────────────────────
_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"), "[REDACTED_GH_TOKEN]"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "[REDACTED_GH_PAT]"),
    (re.compile(r"AIza[0-9A-Za-z\-_]{30,}"), "[REDACTED_GOOGLE_KEY]"),
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "[REDACTED_OPENAI_KEY]"),
    (re.compile(r"sk-ant-[A-Za-z0-9\-_]{20,}"), "[REDACTED_ANTHROPIC_KEY]"),
    (re.compile(r"gsk_[A-Za-z0-9]{20,}"), "[REDACTED_GROQ_KEY]"),
    (re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"), "[REDACTED_JWT]"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL), "[REDACTED_PRIVATE_KEY]"),
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "[REDACTED_EMAIL]"),
)


def redact(text: str) -> str:
    """Strip secrets/PII from a string before logging. Best-effort, fail-open."""
    if not text:
        return text
    try:
        out = text
        for pat, repl in _REDACTIONS:
            out = pat.sub(repl, out)
        return out
    except Exception:
        return "[redaction_error]"


# ──────────────────────────────────────────────────────────────────
# Token estimation — char/4 heuristic (cheap, provider-agnostic). Good enough
# for a daily budget guardrail; Langfuse provides exact token+cost accounting.
# ──────────────────────────────────────────────────────────────────
def estimate_tokens(*texts: str) -> int:
    return sum(len(t or "") for t in texts) // 4


# ──────────────────────────────────────────────────────────────────
# Daily budget cap — per (user, org), UTC-day bucket.
# ──────────────────────────────────────────────────────────────────
def _day_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def check_budget(user_id: int, org: str) -> tuple[bool, int, int]:
    """Return (allowed, used_today, limit). ``allowed`` is False only when a
    positive limit is set AND already met. Fails OPEN on any error."""
    limit = get_settings().daily_token_budget
    if limit <= 0:
        return True, 0, 0
    try:
        doc = await get_db()["usage_daily"].find_one(
            {"user_id": user_id, "org": org.lower(), "day": _day_key()}
        )
        used = int((doc or {}).get("tokens", 0))
        return used < limit, used, limit
    except Exception as exc:
        log.warning("budget check failed (allowing): %s", exc)
        return True, 0, limit


async def record_usage(user_id: int, org: str, tokens: int) -> None:
    """Add ``tokens`` to today's per-(user, org) counter. Fail-open."""
    if tokens <= 0:
        return
    try:
        await get_db()["usage_daily"].update_one(
            {"user_id": user_id, "org": org.lower(), "day": _day_key()},
            {"$inc": {"tokens": tokens}, "$set": {"updated_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
    except Exception as exc:
        log.warning("record_usage failed: %s", exc)


# ──────────────────────────────────────────────────────────────────
# Circuit breaker — process-local, per provider key.
# ──────────────────────────────────────────────────────────────────
_failures: dict[str, int] = {}
_open_until: dict[str, float] = {}


def circuit_open(key: str = "llm") -> bool:
    """True while the breaker for ``key`` is open (cooling down)."""
    until = _open_until.get(key, 0.0)
    if until and time.monotonic() < until:
        return True
    return False


def record_failure(key: str = "llm") -> None:
    s = get_settings()
    _failures[key] = _failures.get(key, 0) + 1
    if _failures[key] >= s.circuit_failure_threshold:
        _open_until[key] = time.monotonic() + s.circuit_cooldown_seconds
        log.warning(
            "circuit '%s' OPEN for %ss after %d failures",
            key, s.circuit_cooldown_seconds, _failures[key],
        )


def record_success(key: str = "llm") -> None:
    _failures[key] = 0
    _open_until.pop(key, None)


# ──────────────────────────────────────────────────────────────────
# Audit log — one structured, redacted record per turn.
# ──────────────────────────────────────────────────────────────────
async def write_audit(
    *,
    user_id: int,
    org: str,
    session_id: str,
    question: str,
    answer: str,
    tool_calls: list[Any],
    tokens: int,
    duration_ms: int,
    provider_order: list[str],
) -> None:
    """Persist a redacted audit entry. Fail-open — never blocks the turn."""
    if not get_settings().audit_log_enabled:
        return
    try:
        tools = []
        for tc in tool_calls or []:
            name = getattr(tc, "name", None) or (tc.get("name") if isinstance(tc, dict) else None)
            args = getattr(tc, "args", None) or (tc.get("args") if isinstance(tc, dict) else {})
            tools.append({"name": name, "args_keys": sorted(args.keys()) if isinstance(args, dict) else []})
        await get_db()["audit_log"].insert_one(
            {
                "timestamp": datetime.now(timezone.utc),
                "actor_user_id": user_id,
                "org": org.lower(),
                "session_id": session_id,
                "event_type": "chat_turn",
                "question": redact(question)[:1000],
                "answer_preview": redact(answer)[:500],
                "tools": tools,
                "tool_count": len(tools),
                "token_estimate": tokens,
                "duration_ms": duration_ms,
                "provider_order": provider_order,
            }
        )
    except Exception as exc:
        log.warning("audit write failed: %s", exc)
