from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from app.clients import github as gh_client
from app.core.config import get_settings
from app.core.db import close_client, get_db, init_indexes
from app.core.errors import register_error_handlers
from app.routers import (
    activity,
    alerts,
    ask,
    chat,
    dashboard,
    digest,
    health,
    leaderboard,
    repos,
    webhooks,
    workspaces,
)
from app.routers import (
    auth as auth_router,
)
from app.routers import (
    settings as settings_router,
)
from app.telemetry.sentry import init_sentry
from app.workers.scheduler import start_scheduler, stop_scheduler


def _register_agent_capabilities() -> None:
    """Import the modules that register optional tool factories so their
    availability is deterministic (not dependent on hot-path import order).

    ``app.agents.tools`` registers the ``web_search`` handler factory;
    ``app.rag.retriever`` registers the ``semantic_search`` factory (only
    when RAG is enabled). Each is guarded so a missing optional dependency
    degrades gracefully to pure-agentic mode instead of breaking boot.
    """
    try:
        import app.agents.tools  # noqa: F401  (sets WEB_SEARCH_HANDLER_FACTORY)
    except Exception as exc:
        print(f"[startup] web-search tool unavailable: {exc}")
    try:
        from app.rag import is_rag_enabled

        if is_rag_enabled():
            import app.rag.retriever  # noqa: F401 (sets SEMANTIC_SEARCH_HANDLER_FACTORY)
            print("[startup] RAG enabled — semantic_search tool registered")
        else:
            print("[startup] RAG disabled — running in pure-agentic mode")
    except Exception as exc:
        print(f"[startup] RAG unavailable: {exc}")


async def _warn_if_public_workspaces_unauthenticated() -> None:
    """Public (open-source) workspaces have no installation token, so they all
    share ONE budget: 5,000 req/hr with a ``GITHUB_PAT``, or 60 req/hr without
    one. At 60/hr a couple of dashboard loads exhaust the hour, so say so
    loudly at boot rather than letting it surface as random 403s.
    """
    if get_settings().github_pat:
        return
    try:
        count = await get_db()["installations"].count_documents({"mode": "public"})
    except Exception:
        return
    if count:
        print(
            f"[startup] WARNING: {count} public workspace(s) and no GITHUB_PAT — "
            "public reads are anonymous (60 req/hr shared by all of them) and "
            "their RAG indexing is disabled. Set GITHUB_PAT to lift both."
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        await init_indexes()
    except Exception as exc:
        # Mongo down? Don't crash — health endpoint will report it.
        print(f"[startup] mongo init skipped: {exc}")
    await _warn_if_public_workspaces_unauthenticated()
    _register_agent_capabilities()
    try:
        start_scheduler()
    except Exception as exc:
        print(f"[startup] scheduler skipped: {exc}")
    yield
    await stop_scheduler()
    await gh_client.close()
    await close_client()


def create_app() -> FastAPI:
    s = get_settings()
    # Before the app object exists, so the SDK's FastAPI integration can hook
    # request handling. No SENTRY_DSN ⇒ no-op.
    if init_sentry(
        s.sentry_dsn,
        environment=s.app_env,
        traces_sample_rate=s.sentry_traces_sample_rate,
        profiles_sample_rate=s.sentry_profiles_sample_rate,
    ):
        print(f"[startup] Sentry error monitoring enabled (env={s.app_env})")
    app = FastAPI(
        title="DyPol.ai API",
        version="0.1.0",
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)

    app.include_router(health.router)
    app.include_router(auth_router.router)
    app.include_router(webhooks.router)
    app.include_router(workspaces.router)
    app.include_router(dashboard.router)
    app.include_router(repos.router)
    app.include_router(leaderboard.router)
    app.include_router(activity.router)
    app.include_router(alerts.router)
    app.include_router(digest.router)
    app.include_router(ask.router)
    app.include_router(chat.router)
    app.include_router(settings_router.router)
    return app


app = create_app()
