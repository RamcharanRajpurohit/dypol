"""Chat service — agentic, multi-turn, tool-using conversations.

Sessions and messages live in Mongo (``chat_sessions`` / ``chat_messages``).
The agentic turn itself is now driven by the provider-agnostic LangGraph agent
in ``app/agents/`` (see ``app.agents.graph.run_agent``), which replaced the two
hand-written provider loops that used to live here. This module owns only the
durable concerns — session CRUD, history load, persistence of the assistant
message + its flat ``ChatToolCall`` trace, auto-titling, and session metadata.

Flow per send():
  1. Persist the user message.
  2. Load prior session history.
  3. Run the LangGraph agent (any configured provider; sub-agents + tools).
  4. Persist the assistant message (with the tool-call trace the UI renders).
  5. Auto-title the session on the first turn; update preview + counters.

A streaming variant (``stream_message``) shares the same persistence via
``_finalize_turn`` and adds live SSE token/tool events.
"""
from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from app.agents.graph import run_agent
from app.agents.providers import is_agent_enabled as _providers_enabled
from app.core.config import get_settings
from app.core.db import get_db
from app.models.schemas import (
    ChatMessage,
    ChatSession,
    ChatToolCall,
    ChatTurnResponse,
)

# The live system prompt now lives in app/agents/prompts.py (built per
# workspace). The old monolithic SYSTEM_INSTRUCTION constant was moved there
# verbatim; the agentic loop itself is app.agents.graph.run_agent.


def is_agent_enabled() -> bool:
    """True if any LLM provider (Claude/OpenAI/Gemini/Groq) is configured."""
    return _providers_enabled()


# ──────────────────────────────────────────────────────────────────
# Mongo helpers
# ──────────────────────────────────────────────────────────────────
def _session_doc_to_model(doc: dict[str, Any]) -> ChatSession:
    return ChatSession(
        id=doc["_id"],
        user_id=doc["user_id"],
        org=doc["org"],
        title=doc["title"],
        pinned=doc.get("pinned", False),
        archived=doc.get("archived", False),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
        message_count=doc.get("message_count", 0),
        last_message_preview=doc.get("last_message_preview"),
    )


def _msg_doc_to_model(doc: dict[str, Any]) -> ChatMessage:
    return ChatMessage(
        id=doc["_id"],
        session_id=doc["session_id"],
        role=doc["role"],
        content=doc["content"],
        tool_calls=[
            ChatToolCall(**tc) for tc in (doc.get("tool_calls") or [])
        ],
        created_at=doc["created_at"],
    )


# ──────────────────────────────────────────────────────────────────
# Session CRUD
# ──────────────────────────────────────────────────────────────────
async def create_session(user_id: int, org: str, title: str = "New chat") -> ChatSession:
    db = get_db()
    now = datetime.now(timezone.utc)
    doc = {
        "_id": uuid.uuid4().hex,
        "user_id": user_id,
        "org": org,
        "title": title,
        "pinned": False,
        "archived": False,
        "created_at": now,
        "updated_at": now,
        "message_count": 0,
        "last_message_preview": None,
    }
    await db["chat_sessions"].insert_one(doc)
    return _session_doc_to_model(doc)


async def list_sessions(
    user_id: int, org: str, include_archived: bool = False, limit: int = 100
) -> list[ChatSession]:
    db = get_db()
    query: dict[str, Any] = {"user_id": user_id, "org": org}
    if not include_archived:
        query["archived"] = {"$ne": True}
    cursor = (
        db["chat_sessions"].find(query).sort([("pinned", -1), ("updated_at", -1)]).limit(limit)
    )
    return [_session_doc_to_model(d) async for d in cursor]


async def get_session(user_id: int, session_id: str) -> ChatSession | None:
    db = get_db()
    doc = await db["chat_sessions"].find_one({"_id": session_id, "user_id": user_id})
    return _session_doc_to_model(doc) if doc else None


async def list_messages(session_id: str, limit: int = 200) -> list[ChatMessage]:
    db = get_db()
    cursor = (
        db["chat_messages"].find({"session_id": session_id}).sort("created_at", 1).limit(limit)
    )
    return [_msg_doc_to_model(d) async for d in cursor]


async def update_session(user_id: int, session_id: str, **fields: Any) -> ChatSession | None:
    db = get_db()
    fields["updated_at"] = datetime.now(timezone.utc)
    res = await db["chat_sessions"].find_one_and_update(
        {"_id": session_id, "user_id": user_id},
        {"$set": fields},
        return_document=True,
    )
    return _session_doc_to_model(res) if res else None


async def delete_session(user_id: int, session_id: str) -> bool:
    db = get_db()
    res = await db["chat_sessions"].delete_one({"_id": session_id, "user_id": user_id})
    if res.deleted_count:
        await db["chat_messages"].delete_many({"session_id": session_id})
        return True
    return False


# ──────────────────────────────────────────────────────────────────
# Title generation — short, deterministic-ish first-message slug
# ──────────────────────────────────────────────────────────────────
def _slug_title(text: str, max_len: int = 60) -> str:
    cleaned = " ".join(text.strip().split())
    if len(cleaned) <= max_len:
        return cleaned or "New chat"
    return cleaned[: max_len - 1].rstrip() + "…"


# ──────────────────────────────────────────────────────────────────
# Sending a message — the agentic loop
# ──────────────────────────────────────────────────────────────────
async def _persist_message(
    session_id: str,
    role: str,
    content: str,
    tool_calls: list[ChatToolCall] | None = None,
) -> ChatMessage:
    db = get_db()
    doc = {
        "_id": uuid.uuid4().hex,
        "session_id": session_id,
        "role": role,
        "content": content,
        "tool_calls": [tc.model_dump() for tc in (tool_calls or [])],
        "created_at": datetime.now(timezone.utc),
    }
    await db["chat_messages"].insert_one(doc)
    return _msg_doc_to_model(doc)


# ──────────────────────────────────────────────────────────────────
# One agentic turn — persist, run the LangGraph agent, persist, return.
# ──────────────────────────────────────────────────────────────────
async def _finalize_turn(
    user_id: int,
    session: ChatSession,
    session_id: str,
    user_content: str,
    final_text: str,
    tool_trace: list[ChatToolCall],
    user_msg: ChatMessage,
    already_persisted_assistant: ChatMessage | None = None,
) -> ChatTurnResponse:
    """Persist the assistant message + trace, auto-title, bump session
    metadata, and return the full turn. Shared by the streaming and
    non-streaming paths so persistence is identical.

    ``already_persisted_assistant`` — when the caller already wrote the
    assistant message (e.g. a budget-limit notice), reuse it instead of
    persisting a duplicate."""
    db = get_db()
    assistant_msg = already_persisted_assistant or await _persist_message(
        session_id, "assistant", final_text, tool_trace
    )

    new_title = session.title
    # Title on the first turn that produces one. Previously this also required
    # ``message_count == 0``, which a drifted counter could falsely fail — the
    # placeholder check alone is both sufficient and self-correcting.
    if session.title in {"New chat", ""} or session.title.startswith("New chat"):
        new_title = _slug_title(user_content)

    # Count the messages instead of blindly incrementing by 2. The user message
    # is persisted BEFORE the model runs, so any turn that died in between (a
    # provider error, a dropped stream) left the message stored but the counter
    # un-incremented — 5 of 17 sessions had drifted, and sessions whose very
    # first turn failed showed 0 despite having messages. Counting is exact,
    # uses the existing (session_id, created_at) index, and heals old drift on
    # the next completed turn.
    total = await db["chat_messages"].count_documents({"session_id": session_id})

    await db["chat_sessions"].update_one(
        {"_id": session_id},
        {
            "$set": {
                "title": new_title,
                "updated_at": datetime.now(timezone.utc),
                "last_message_preview": _slug_title(final_text, 140),
                "message_count": total,
            }
        },
    )
    updated = await get_session(user_id, session_id)
    assert updated is not None
    return ChatTurnResponse(
        session=updated, user_message=user_msg, assistant_message=assistant_msg
    )


async def _turn_context(
    user_id: int, install: dict[str, Any]
) -> tuple[dict[str, Any], str]:
    """Prepare per-turn agent context: an install dict tagged with the user id
    (so the ``remember`` tool can scope writes) and the user's long-term memory
    block to inject into the system prompt."""
    bound_install = {**install, "_user_id": user_id}
    try:
        from app.services.user_memory import memory_prompt_block

        org = install.get("account_login", "")
        memory_block = await memory_prompt_block(user_id, org)
    except Exception:
        memory_block = ""
    return bound_install, memory_block


def _governance():
    """Lazy import of the governance module (cost/circuit/audit)."""
    from app.services import governance

    return governance


async def _post_turn_governance(
    user_id: int,
    org: str,
    session_id: str,
    question: str,
    answer: str,
    tool_trace: list[ChatToolCall],
    duration_ms: int,
) -> None:
    """Record token usage and write a redacted audit entry. Fail-open."""
    try:
        gov = _governance()
        tool_text = " ".join(
            (tc.result_preview or "") for tc in tool_trace
        )
        tokens = gov.estimate_tokens(question, answer, tool_text)
        await gov.record_usage(user_id, org, tokens)
        await gov.write_audit(
            user_id=user_id,
            org=org,
            session_id=session_id,
            question=question,
            answer=answer,
            tool_calls=tool_trace,
            tokens=tokens,
            duration_ms=duration_ms,
            provider_order=get_settings().provider_order_list,
        )
    except Exception:
        pass


async def send_message(
    user_id: int, install: dict[str, Any], session_id: str, content: str
) -> ChatTurnResponse:
    """Run one turn: persist the user message, drive the provider-agnostic
    LangGraph agent (any configured provider, with sub-agents + tools), persist
    the assistant message + its flat tool trace, and return the full pair.

    The agent's provider fallback chain (default Gemini → Groq; Claude/OpenAI
    when keys are added) lives inside ``app.agents.graph``; this function no
    longer branches per provider.
    """
    if not is_agent_enabled():
        raise RuntimeError(
            "No LLM provider configured (set GEMINI_API_KEY, GROQ_API_KEY, "
            "ANTHROPIC_API_KEY, or OPENAI_API_KEY)"
        )

    session = await get_session(user_id, session_id)
    if session is None:
        raise ValueError("session_not_found")

    org = install.get("account_login", "")
    # Cost control: refuse the turn if today's per-(user, org) budget is spent.
    allowed, used, limit = await _governance().check_budget(user_id, org)
    if not allowed:
        user_msg = await _persist_message(session_id, "user", content)
        msg = (
            f"You've reached today's usage limit ({used:,}/{limit:,} tokens). "
            "It resets at midnight UTC."
        )
        assistant_msg = await _persist_message(session_id, "assistant", msg, [])
        return await _finalize_turn(
            user_id, session, session_id, content, msg, [], user_msg,
            already_persisted_assistant=assistant_msg,
        )

    user_msg = await _persist_message(session_id, "user", content)

    # Prior history EXCLUDING the just-persisted user message (run_agent appends
    # the new turn itself). list_messages returns oldest→newest, so drop the last.
    prior = (await list_messages(session_id))[:-1]

    bound_install, memory_block = await _turn_context(user_id, install)
    t0 = time.monotonic()
    final_text, trace_dicts = await run_agent(
        bound_install, prior, content, extra_context=memory_block,
        obs={"user_id": user_id, "org": org, "session_id": session_id},
    )
    duration_ms = int((time.monotonic() - t0) * 1000)
    tool_trace = [ChatToolCall(**tc) for tc in trace_dicts]

    await _post_turn_governance(
        user_id, org, session_id, content, final_text, tool_trace, duration_ms
    )

    return await _finalize_turn(
        user_id, session, session_id, content, final_text, tool_trace, user_msg
    )


async def stream_message(
    user_id: int, install: dict[str, Any], session_id: str, content: str
) -> AsyncIterator[bytes]:
    """Streaming variant of :func:`send_message` — yields Server-Sent Events.

    Frames (each ``event: <type>\n`` then ``data: <json>\n\n``):
      * ``token`` — a text delta of the answer as the model generates it
                    (the live "typing" effect); ``{"delta": "..."}``.
      * ``tool``  — a tool / sub-agent step as it's recorded (live trace).
      * ``done``  — the final persisted ChatTurnResponse (same shape as the
                    non-streaming endpoint, so the client commits identically).
      * ``error`` — a fatal error message.

    The persisted message + trace are authoritative (captured by the agent's
    tracer), not reconstructed from these events — so the ``done`` frame always
    matches the non-streaming endpoint exactly.
    """
    import asyncio
    import json as _json

    from app.agents.graph import stream_agent

    def _frame(event: str, data: Any) -> bytes:
        return f"event: {event}\ndata: {_json.dumps(data, default=str)}\n\n".encode()

    if not is_agent_enabled():
        yield _frame("error", {"message": "No LLM provider configured."})
        return

    session = await get_session(user_id, session_id)
    if session is None:
        yield _frame("error", {"message": "session_not_found"})
        return

    org = install.get("account_login", "")
    allowed, used, limit = await _governance().check_budget(user_id, org)
    if not allowed:
        user_msg = await _persist_message(session_id, "user", content)
        msg = (
            f"You've reached today's usage limit ({used:,}/{limit:,} tokens). "
            "It resets at midnight UTC."
        )
        a = await _persist_message(session_id, "assistant", msg, [])
        turn = await _finalize_turn(
            user_id, session, session_id, content, msg, [], user_msg,
            already_persisted_assistant=a,
        )
        yield _frame("done", turn.model_dump(mode="json"))
        return

    user_msg = await _persist_message(session_id, "user", content)
    prior = (await list_messages(session_id))[:-1]
    _t0 = time.monotonic()

    # Bridge the agent's synchronous emit callbacks to this async stream via a
    # queue: the graph fires token_emit(delta) per generated chunk and emit(row)
    # per tool/sub-agent step from inside the run; we drain the queue and yield
    # the matching SSE frames as they arrive (live typing + live trace).
    queue: asyncio.Queue = asyncio.Queue()

    def _emit(row: dict[str, Any]) -> None:
        queue.put_nowait(("tool", row))

    def _token_emit(delta: str) -> None:
        queue.put_nowait(("token", {"delta": delta}))

    bound_install, memory_block = await _turn_context(user_id, install)

    async def _drive() -> tuple[str, list[dict[str, Any]]]:
        try:
            return await stream_agent(
                bound_install,
                prior,
                content,
                emit=_emit,
                token_emit=_token_emit,
                extra_context=memory_block,
                obs={"user_id": user_id, "org": org, "session_id": session_id},
            )
        finally:
            queue.put_nowait(("__done__", None))

    task = asyncio.ensure_future(_drive())
    try:
        while True:
            kind, payload = await queue.get()
            if kind == "__done__":
                break
            yield _frame(kind, payload)
        final_text, trace_dicts = await task
    except Exception as exc:  # pragma: no cover - defensive
        yield _frame("error", {"message": str(exc)})
        return

    tool_trace = [ChatToolCall(**tc) for tc in trace_dicts]
    await _post_turn_governance(
        user_id, org, session_id, content, final_text, tool_trace,
        int((time.monotonic() - _t0) * 1000),
    )
    turn = await _finalize_turn(
        user_id, session, session_id, content, final_text, tool_trace, user_msg
    )
    yield _frame("done", turn.model_dump(mode="json"))

