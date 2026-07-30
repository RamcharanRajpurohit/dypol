"""Thin wrapper around the Google Gemini API.

Clients are built per key from the rotating pool (``app/core/keypool.py``)
and cached, so successive calls spread across every configured key instead of
hammering one project's quota. Falls back gracefully if no key is set —
callers can branch on ``is_enabled()``.
"""
from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.core.keypool import gemini_keys, next_gemini_key

_clients: dict[str, Any] = {}


def is_enabled() -> bool:
    return bool(gemini_keys())


def _get_client() -> Any:
    """Returns a google-genai Client bound to the next key in the pool."""
    key = next_gemini_key()
    if not key:
        raise RuntimeError("No Gemini key set (GEMINI_API_KEY or GEMINI_API_KEY_1..8)")
    client = _clients.get(key)
    if client is None:
        # Imported lazily so the rest of the app boots even without the dep.
        from google import genai  # type: ignore[import-untyped]

        client = genai.Client(api_key=key)
        _clients[key] = client
    return client


async def generate(prompt: str, system: str | None = None) -> str:
    """Single-shot text generation.

    Returns the model's text response. The Gemini SDK's ``generate_content``
    is sync; we run it in a thread to avoid blocking the event loop.
    """
    import asyncio

    client = _get_client()
    s = get_settings()

    def _run() -> str:
        config: dict[str, Any] = {}
        if system:
            config["system_instruction"] = system
        resp = client.models.generate_content(
            model=s.gemini_model,
            contents=prompt,
            config=config or None,
        )
        return getattr(resp, "text", "") or ""

    return await asyncio.to_thread(_run)


def is_quota_error(exc: BaseException) -> bool:
    """True if the exception is Gemini's 429 quota response."""
    msg = str(exc)
    return "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower() or "429" in msg
