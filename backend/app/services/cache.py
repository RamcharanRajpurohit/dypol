"""Tiny in-memory TTL cache + Mongo-backed cache helpers.

Used to dampen GitHub rate-limit pressure for hot endpoints.
"""
from __future__ import annotations

import time
from typing import Any

_store: dict[str, tuple[float, Any]] = {}


def get(key: str) -> Any | None:
    entry = _store.get(key)
    if entry is None:
        return None
    expires_at, value = entry
    if expires_at < time.time():
        _store.pop(key, None)
        return None
    return value


def set_(key: str, value: Any, ttl: int) -> None:
    _store[key] = (time.time() + ttl, value)


def clear() -> None:
    _store.clear()
