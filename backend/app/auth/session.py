"""Stateless signed-cookie sessions.

The cookie payload is a small JSON dict (user id, github login, issued-at).
It is signed with HMAC-SHA256 via itsdangerous so the user cannot tamper.
No DB lookup per request — fast and horizontally scalable.

Logout = clear the cookie.
Force-logout-everyone = rotate ``SESSION_SECRET`` (every cookie becomes invalid).
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import Request, Response
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner

from app.core.config import get_settings


def _signer() -> TimestampSigner:
    return TimestampSigner(get_settings().session_secret, salt="dypol.session")


def write_session(response: Response, payload: dict[str, Any]) -> None:
    s = get_settings()
    raw = json.dumps(payload, separators=(",", ":")).encode()
    signed = _signer().sign(raw).decode()
    response.set_cookie(
        key=s.session_cookie_name,
        value=signed,
        max_age=s.session_max_age_seconds,
        httponly=True,
        secure=s.is_prod,
        samesite="none" if s.is_prod else "lax",
        path="/",
    )


def clear_session(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(key=s.session_cookie_name, path="/")


def read_session(request: Request) -> dict[str, Any] | None:
    s = get_settings()
    raw = request.cookies.get(s.session_cookie_name)
    if not raw:
        return None
    try:
        unsigned = _signer().unsign(raw, max_age=s.session_max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None
    try:
        return json.loads(unsigned)
    except json.JSONDecodeError:
        return None
