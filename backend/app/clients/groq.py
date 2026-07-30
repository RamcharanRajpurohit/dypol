"""Thin wrapper around the Groq API (OpenAI-compatible).

Groq exposes an OpenAI-compatible chat-completions endpoint with very fast
inference and a generous free tier. We use it as the primary LLM for the
agentic chat (function calling + multi-turn). Gemini stays around as a
fallback (see ``services/chat.py``).

Lazy-instantiated singleton, async wrappers via ``asyncio.to_thread``.
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.core.config import get_settings

_client: Any | None = None


def is_enabled() -> bool:
    return bool(get_settings().groq_api_key)


def _get_client() -> Any:
    global _client
    if _client is not None:
        return _client
    s = get_settings()
    if not s.groq_api_key:
        raise RuntimeError("GROQ_API_KEY not set")
    from groq import Groq  # type: ignore[import-untyped]

    _client = Groq(api_key=s.groq_api_key)
    return _client


async def chat_completion(
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict | None = None,
    temperature: float = 0.2,
    max_tokens: int | None = None,
) -> Any:
    """One round-trip to Groq's chat completions endpoint.

    ``messages``: OpenAI-style [{role, content, tool_calls?, tool_call_id?}].
    ``tools``: list of OpenAI-style function definitions, optional.
    Returns the SDK's response object — caller inspects choices[0].message.
    """
    client = _get_client()

    def _run() -> Any:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
            if tool_choice is not None:
                kwargs["tool_choice"] = tool_choice
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        return client.chat.completions.create(**kwargs)

    return await asyncio.to_thread(_run)


def is_quota_error(exc: BaseException) -> bool:
    """True if the exception looks like a Groq rate-limit / quota response."""
    msg = str(exc).lower()
    return (
        "rate_limit_exceeded" in msg
        or "rate limit" in msg
        or "429" in msg
        or "quota" in msg
        or "too many requests" in msg
    )
