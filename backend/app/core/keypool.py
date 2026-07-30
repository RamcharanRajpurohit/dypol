"""Round-robin rotation across multiple provider API keys.

Gemini free-tier quota is per *project*, so several keys from different
projects give genuinely independent budgets. Handing every request the same
key wastes that: one key burns through its RPM/RPD while the others idle.

``next_gemini_key()`` returns the next key each time it's called, so
consecutive model constructions land on different keys. It also composes with
the agent's existing quota fallback (``agents/providers.model_chain()``): when
a call fails with RESOURCE_EXHAUSTED the graph retries the next chain step,
which builds a new model — and therefore picks up a different key.

Rotation state is process-local and reset automatically if the configured key
list changes.
"""
from __future__ import annotations

import itertools
import threading
from collections.abc import Iterator

from app.core.config import get_settings

_lock = threading.Lock()
_cycle: Iterator[str] | None = None
_snapshot: tuple[str, ...] = ()


def gemini_keys() -> list[str]:
    """All configured Gemini keys, primary first."""
    return get_settings().gemini_api_key_list


def next_gemini_key() -> str | None:
    """Next Gemini key in round-robin order, or None if none are configured."""
    global _cycle, _snapshot
    keys = tuple(gemini_keys())
    if not keys:
        return None
    with _lock:
        if keys != _snapshot or _cycle is None:
            _snapshot = keys
            _cycle = itertools.cycle(keys)
        return next(_cycle)


def describe_pool() -> str:
    """Redacted one-line summary for startup logs — never print a whole key."""
    keys = gemini_keys()
    if not keys:
        return "no Gemini keys configured"
    return f"{len(keys)} Gemini key(s): " + ", ".join(f"…{k[-6:]}" for k in keys)
