"""Sentry error monitoring — optional, inert without a DSN.

Domain-free like the rest of ``app.telemetry``: no imports from ``app.*``.
The caller (``app.main``) passes settings values in. The SDK's FastAPI /
Starlette / httpx / pymongo integrations auto-enable when those packages are
importable, so a bare ``init`` here captures unhandled request exceptions,
outbound HTTP breadcrumbs, and Mongo query breadcrumbs with no per-router
wiring.
"""

from __future__ import annotations


def init_sentry(
    dsn: str | None,
    *,
    environment: str = "dev",
    traces_sample_rate: float = 0.0,
    profiles_sample_rate: float = 0.0,
    release: str | None = None,
) -> bool:
    """Initialise the Sentry SDK. Returns True when active.

    No DSN or missing ``sentry-sdk`` package ⇒ no-op (returns False) so the
    app boots unchanged, mirroring how Langfuse is gated on its keys.
    """
    if not dsn:
        return False
    try:
        import sentry_sdk
    except ImportError:
        print("[startup] SENTRY_DSN set but sentry-sdk not installed — "
              'run: uv pip install -e ".[sentry]"')
        return False
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release,
        traces_sample_rate=traces_sample_rate,
        profiles_sample_rate=profiles_sample_rate,
        # Errors only unless PII capture is deliberately turned on later;
        # request bodies/headers stay out of events by default.
        send_default_pii=False,
    )
    return True
