"""Cross-chat user memory — durable facts the agent recalls across sessions.

Each chat session is otherwise isolated. This gives DyPol a long-term memory
scoped to (user, org): facts the user states or the agent learns ("we use trunk-
based dev", "focus on the billing team", "I prefer terse answers", "our release
day is Thursday"). These are injected into the system prompt of EVERY new chat so
the agent starts informed, and the agent can write new ones mid-conversation via
the ``remember`` tool.

Storage: Mongo collection ``user_memory`` — one document per (user_id, org),
holding a capped list of memory entries. Cheap to read (one doc) and bounded so
it never bloats the prompt.

Scope choice: keyed by (user_id, org) — memories are per person per workspace,
matching how chat sessions are scoped. A user working across two orgs keeps
separate memory for each.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.db import get_db

# Keep memory bounded so it can always be injected into the prompt cheaply.
MAX_ENTRIES = 40
MAX_ENTRY_CHARS = 400
# How much of the memory to inject into a prompt (most-recent / highest-signal).
PROMPT_ENTRIES = 25


def _doc_key(user_id: int, org: str) -> dict[str, Any]:
    return {"user_id": user_id, "org": org.lower()}


async def get_memories(user_id: int, org: str) -> list[dict[str, Any]]:
    """Return this user's memory entries for ``org`` (newest first)."""
    doc = await get_db()["user_memory"].find_one(_doc_key(user_id, org))
    if not doc:
        return []
    return list(doc.get("entries", []))


async def add_memory(
    user_id: int, org: str, text: str, *, category: str = "fact"
) -> dict[str, Any]:
    """Append a durable memory. De-dupes on exact text; trims to MAX_ENTRIES.

    ``category`` — a light tag (e.g. ``fact`` / ``preference`` / ``context``)
    purely for display + the agent's own organization. Returns the new entry.
    """
    text = (text or "").strip()[:MAX_ENTRY_CHARS]
    if not text:
        raise ValueError("empty_memory")

    db = get_db()
    key = _doc_key(user_id, org)
    now = datetime.now(timezone.utc)
    existing = await get_memories(user_id, org)

    # Skip exact duplicates (case-insensitive) — just bump nothing.
    if any(e.get("text", "").strip().lower() == text.lower() for e in existing):
        return {"text": text, "category": category, "deduped": True}

    entry = {
        "id": uuid.uuid4().hex,
        "text": text,
        "category": category,
        "created_at": now,
    }
    # Newest first; cap the list.
    entries = [entry, *existing][:MAX_ENTRIES]
    await db["user_memory"].update_one(
        key,
        {
            "$set": {**key, "entries": entries, "updated_at": now},
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    return entry


async def delete_memory(user_id: int, org: str, entry_id: str) -> bool:
    """Remove one memory by id. Returns True if something was removed."""
    db = get_db()
    res = await db["user_memory"].update_one(
        _doc_key(user_id, org), {"$pull": {"entries": {"id": entry_id}}}
    )
    return res.modified_count > 0


async def clear_memories(user_id: int, org: str) -> None:
    await get_db()["user_memory"].delete_one(_doc_key(user_id, org))


async def memory_prompt_block(user_id: int, org: str) -> str:
    """Render the user's memory as a prompt section, or "" if none.

    Injected into the system prompt of every turn so the agent always has the
    long-term context. Capped to ``PROMPT_ENTRIES`` newest entries.
    """
    entries = await get_memories(user_id, org)
    if not entries:
        return ""
    lines = [
        f"- {e.get('text','')}" for e in entries[:PROMPT_ENTRIES] if e.get("text")
    ]
    if not lines:
        return ""
    body = "\n".join(lines)
    return (
        "\n\nWHAT YOU KNOW ABOUT THIS USER / WORKSPACE (long-term memory, carried "
        "across all their chats — use it to personalize and stay consistent; do "
        "not re-ask for things stated here):\n" + body + "\n"
    )
