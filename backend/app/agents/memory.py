"""Memory — Mongo↔LangChain message mapping, history trimming, summaries.

Three responsibilities:

  * ``messages_from_mongo`` — turn stored ChatMessage docs into LangChain
    ``BaseMessage`` objects for replay. We deliberately do NOT re-emit stored
    tool calls as ``ToolMessage``s: we never persisted the raw tool *outputs*,
    so replaying tool_call ids with no matching results would leave dangling
    tool_call_ids that providers (OpenAI/Anthropic) reject.
  * ``trim_history`` — keep the message list under a token budget using
    ``trim_messages`` with a tiktoken-based counter (best-effort; falls back
    to a char/4 heuristic, and to the untrimmed list on any error).
  * ``summarize_overflow`` — fold dropped turns + the prior running summary
    into a compact (<=200 word) running summary, best-effort.

Everything heavy/optional (tiktoken) is imported lazily inside functions.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel


# Phrases that mark an assistant turn as a content-free greeting. Replaying
# these into history makes tool-calling models (esp. Gemini) ECHO the greeting
# instead of answering the next question, so we drop them — they carry no
# information worth keeping for continuity.
_GREETING_MARKERS = (
    "how can i assist you",
    "how can i help you",
    "what would you like to know",
    "i'm ready to help",
    "i am ready to help",
    "how may i assist",
)


def _is_pure_greeting(text: str) -> bool:
    t = text.strip().lower()
    if not t or len(t) > 320:
        return False
    starts_greeting = t.startswith(("hello", "hi ", "hi!", "hey", "i'm dypol", "i am dypol"))
    has_offer = any(marker in t for marker in _GREETING_MARKERS)
    return starts_greeting and has_offer


def messages_from_mongo(prior: list[Any]) -> list[BaseMessage]:
    """Map stored ChatMessage-like items → LangChain messages.

    Each item has ``.role`` ("user"|"assistant"|"system") and ``.content``
    (str). user→HumanMessage, assistant→AIMessage. We skip ``system`` (the
    live system prompt is rebuilt each turn) and we do NOT replay tool traces
    — there are no stored tool outputs, so reconstructing tool_call ids would
    break provider validation.

    Pure-greeting assistant turns are dropped: they have no informational value
    and replaying them makes the model parrot the greeting on the next turn
    instead of answering. The matching user "hi" stays (harmless context).
    """
    out: list[BaseMessage] = []
    for m in prior:
        role = getattr(m, "role", None)
        content = getattr(m, "content", "") or ""
        if role == "user":
            out.append(HumanMessage(content=content))
        elif role == "assistant":
            if _is_pure_greeting(content):
                continue  # drop content-free greetings (anti-parrot)
            # Plain text only — never attach tool_calls (no stored outputs).
            out.append(AIMessage(content=content))
        # system / anything else → skip
    return out


def _token_counter() -> Any:
    """Return a ``token_counter`` callable for ``trim_messages``.

    Prefers a tiktoken-backed counter; on any failure (model lookup, missing
    dep) falls back to a cheap char/4 heuristic. The returned callable accepts
    a list of messages and returns an int token estimate.
    """
    try:
        import tiktoken

        try:
            enc = tiktoken.get_encoding("cl100k_base")
        except Exception:
            enc = tiktoken.encoding_for_model("gpt-4o")

        def _count(messages: list[BaseMessage]) -> int:
            total = 0
            for m in messages:
                content = m.content
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    text = " ".join(
                        part.get("text", "") if isinstance(part, dict) else str(part)
                        for part in content
                    )
                else:
                    text = str(content)
                # +4 per message for role/formatting overhead, like OpenAI's guide.
                total += len(enc.encode(text)) + 4
            return total

        return _count
    except Exception:
        def _count_heuristic(messages: list[BaseMessage]) -> int:
            total = 0
            for m in messages:
                content = m.content
                text = content if isinstance(content, str) else str(content)
                total += (len(text) // 4) + 4
            return total

        return _count_heuristic


def trim_history(messages: list[BaseMessage], max_tokens: int) -> list[BaseMessage]:
    """Trim ``messages`` to fit ``max_tokens``, keeping the most recent turns.

    Uses ``trim_messages`` (strategy="last", include_system=True,
    start_on="human"). Robust: returns the original list unchanged on any
    error so a trimming hiccup never drops the user's actual question.
    """
    try:
        from langchain_core.messages import trim_messages

        return trim_messages(
            messages,
            max_tokens=max_tokens,
            token_counter=_token_counter(),
            strategy="last",
            include_system=True,
            start_on="human",
        )
    except Exception:
        return messages


async def summarize_overflow(
    dropped_messages: list[BaseMessage],
    prior_summary: str,
    model: BaseChatModel,
) -> str:
    """Fold ``dropped_messages`` + ``prior_summary`` into a <=200-word running
    summary. Best-effort: returns ``prior_summary`` unchanged if nothing was
    dropped or on any error."""
    if not dropped_messages:
        return prior_summary

    transcript_lines: list[str] = []
    for m in dropped_messages:
        if isinstance(m, SystemMessage):
            continue
        role = "User" if isinstance(m, HumanMessage) else (
            "Assistant" if isinstance(m, AIMessage) else type(m).__name__
        )
        content = m.content
        text = content if isinstance(content, str) else str(content)
        if text.strip():
            transcript_lines.append(f"{role}: {text.strip()}")

    if not transcript_lines:
        return prior_summary

    transcript = "\n".join(transcript_lines)
    prompt = (
        "You maintain a concise running summary of an ongoing engineering-analyst "
        "conversation so older turns can be dropped from context without losing "
        "continuity.\n\n"
        f"EXISTING SUMMARY (may be empty):\n{prior_summary or '(none)'}\n\n"
        f"NEW TURNS TO FOLD IN:\n{transcript}\n\n"
        "Rewrite the running summary so it captures the durable facts, decisions, "
        "entities (repos, people, PRs), and open threads from BOTH the existing "
        "summary and the new turns. Keep it under 200 words. Output ONLY the "
        "summary text — no preamble."
    )
    try:
        resp = await model.ainvoke(prompt)
        content = getattr(resp, "content", resp)
        if isinstance(content, list):
            text = " ".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        else:
            text = str(content)
        text = text.strip()
        return text or prior_summary
    except Exception:
        return prior_summary
