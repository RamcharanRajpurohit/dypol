"""Extract token usage from a LangChain response, across providers.

Providers disagree on where usage lives. LangChain normalises most of it onto
``AIMessage.usage_metadata``, but not every integration populates it, so this
falls back through the raw provider payloads rather than silently reporting
zero tokens — a zero would read as "this call was free" in the cost table.
"""
from __future__ import annotations

from typing import Any


def extract_usage(message: Any) -> tuple[int, int]:
    """Return ``(input_tokens, output_tokens)``; ``(0, 0)`` if unknown."""
    # 1. LangChain's normalised field (most integrations, including Gemini).
    meta = getattr(message, "usage_metadata", None)
    if isinstance(meta, dict):
        it = meta.get("input_tokens")
        ot = meta.get("output_tokens")
        if it is not None or ot is not None:
            return int(it or 0), int(ot or 0)

    # 2. response_metadata — provider-specific shapes.
    rm = getattr(message, "response_metadata", None) or {}
    if isinstance(rm, dict):
        # OpenAI / Groq style
        usage = rm.get("token_usage") or rm.get("usage") or {}
        if isinstance(usage, dict):
            it = usage.get("prompt_tokens", usage.get("input_tokens"))
            ot = usage.get("completion_tokens", usage.get("output_tokens"))
            if it is not None or ot is not None:
                return int(it or 0), int(ot or 0)
        # Google GenAI style
        google = rm.get("usage_metadata") or {}
        if isinstance(google, dict):
            it = google.get("prompt_token_count")
            ot = google.get("candidates_token_count")
            if it is not None or ot is not None:
                return int(it or 0), int(ot or 0)

    return 0, 0


def model_name_of(message: Any, fallback: str = "") -> str:
    """Best-effort model id from a response, for pricing lookup."""
    rm = getattr(message, "response_metadata", None) or {}
    if isinstance(rm, dict):
        for key in ("model_name", "model", "model_version"):
            value = rm.get(key)
            if isinstance(value, str) and value:
                return value
    return fallback
