from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # GitHub App
    github_app_id: str = Field(..., alias="GITHUB_APP_ID")
    github_app_slug: str = Field("dypol", alias="GITHUB_APP_SLUG")
    github_app_client_id: str = Field(..., alias="GITHUB_APP_CLIENT_ID")
    github_app_client_secret: str = Field(..., alias="GITHUB_APP_CLIENT_SECRET")
    github_app_private_key: str | None = Field(None, alias="GITHUB_APP_PRIVATE_KEY")
    github_app_private_key_path: str | None = Field(None, alias="GITHUB_APP_PRIVATE_KEY_PATH")
    github_app_webhook_secret: str = Field("", alias="GITHUB_APP_WEBHOOK_SECRET")
    github_api_base: str = Field("https://api.github.com", alias="GITHUB_API_BASE")
    github_pat: str | None = Field(None, alias="GITHUB_PAT")

    # ──────────────────────────────────────────────────────────────
    # LLM providers — the agent (app/agents/) is provider-agnostic via
    # LangChain's init_chat_model. Any provider whose key is set becomes
    # available; AGENT_PROVIDER_ORDER decides the fallback priority.
    # ──────────────────────────────────────────────────────────────

    # Groq — fast (~10x Gemini), generous free tier (30 RPM).
    # gpt-oss-120b is the best reasoning + tool-use model on Groq.
    groq_api_key: str | None = Field(None, alias="GROQ_API_KEY")
    groq_model: str = Field("openai/gpt-oss-120b", alias="GROQ_MODEL")
    groq_fallback_model: str = Field(
        "openai/gpt-oss-20b", alias="GROQ_FALLBACK_MODEL"
    )

    # Gemini — also used for legacy Ask Anything (services/ask.py) and as
    # the default RAG embedder (embed_content) so RAG works with no extra key.
    # Multiple keys are supported: GEMINI_API_KEY plus GEMINI_API_KEY_1..8.
    # Keys from separate Google projects have SEPARATE free-tier quotas, so
    # rotating across them multiplies throughput and survives a single key
    # hitting RESOURCE_EXHAUSTED. See app/core/keypool.py.
    gemini_api_key: str | None = Field(None, alias="GEMINI_API_KEY")
    gemini_api_key_1: str | None = Field(None, alias="GEMINI_API_KEY_1")
    gemini_api_key_2: str | None = Field(None, alias="GEMINI_API_KEY_2")
    gemini_api_key_3: str | None = Field(None, alias="GEMINI_API_KEY_3")
    gemini_api_key_4: str | None = Field(None, alias="GEMINI_API_KEY_4")
    gemini_api_key_5: str | None = Field(None, alias="GEMINI_API_KEY_5")
    gemini_api_key_6: str | None = Field(None, alias="GEMINI_API_KEY_6")
    gemini_api_key_7: str | None = Field(None, alias="GEMINI_API_KEY_7")
    gemini_api_key_8: str | None = Field(None, alias="GEMINI_API_KEY_8")
    gemini_model: str = Field("gemini-2.5-flash", alias="GEMINI_MODEL")
    gemini_fallback_model: str = Field(
        "gemini-2.5-flash-lite", alias="GEMINI_FALLBACK_MODEL"
    )

    # Anthropic (Claude) — wired and ready; dormant until a key is set.
    anthropic_api_key: str | None = Field(None, alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field("claude-sonnet-4-6", alias="ANTHROPIC_MODEL")
    anthropic_fallback_model: str = Field(
        "claude-haiku-4-5-20251001", alias="ANTHROPIC_FALLBACK_MODEL"
    )

    # OpenAI — wired and ready; dormant until a key is set.
    openai_api_key: str | None = Field(None, alias="OPENAI_API_KEY")
    openai_model: str = Field("gpt-4o", alias="OPENAI_MODEL")
    openai_fallback_model: str = Field("gpt-4o-mini", alias="OPENAI_FALLBACK_MODEL")

    # ──────────────────────────────────────────────────────────────
    # Agent behaviour & routing
    # ──────────────────────────────────────────────────────────────
    # Comma-separated provider keys in fallback priority order. Default
    # leads with the keys you already have (Gemini → Groq). Set e.g.
    # "anthropic,openai,groq,gemini" to lead with Claude once a key is added.
    agent_provider_order: str = Field("gemini,groq", alias="AGENT_PROVIDER_ORDER")
    agent_temperature: float = Field(0.2, alias="AGENT_TEMPERATURE")
    agent_max_tokens: int = Field(1200, alias="AGENT_MAX_TOKENS")
    agent_max_tool_turns: int = Field(6, alias="AGENT_MAX_TOOL_TURNS")
    # Context management: trim history to this token budget before each LLM
    # call; fold older turns into a running summary once they exceed N msgs.
    agent_history_token_budget: int = Field(12000, alias="AGENT_HISTORY_TOKEN_BUDGET")
    agent_summarize_after_messages: int = Field(
        20, alias="AGENT_SUMMARIZE_AFTER_MESSAGES"
    )

    # Per-role model overrides for sub-agents (app/agents/subagents). Blank
    # ⇒ the role uses a sensible default derived from the provider's primary
    # (strong roles) or fallback (cheap roles) model. Format: "provider:model"
    # e.g. "groq:openai/gpt-oss-20b" or "anthropic:claude-haiku-4-5-20251001".
    agent_router_model: str | None = Field(None, alias="AGENT_ROUTER_MODEL")
    agent_analyst_model: str | None = Field(None, alias="AGENT_ANALYST_MODEL")
    agent_web_model: str | None = Field(None, alias="AGENT_WEB_MODEL")
    agent_synth_model: str | None = Field(None, alias="AGENT_SYNTH_MODEL")

    # ──────────────────────────────────────────────────────────────
    # Observability — Langfuse agent tracing/evals (optional). With no keys
    # the agent runs unchanged; set both keys to enable per-step traces, token/
    # cost accounting, and LLM-as-judge / regression evals in the Langfuse UI.
    # ──────────────────────────────────────────────────────────────
    langfuse_public_key: str | None = Field(None, alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str | None = Field(None, alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field("https://cloud.langfuse.com", alias="LANGFUSE_HOST")

    # Sentry error monitoring (optional). Inert without SENTRY_DSN; environment
    # tags follow APP_ENV. Traces sampling covers FastAPI request performance —
    # keep it low in prod (it bills against the transactions quota).
    sentry_dsn: str | None = Field(None, alias="SENTRY_DSN")
    sentry_traces_sample_rate: float = Field(0.1, alias="SENTRY_TRACES_SAMPLE_RATE")
    sentry_profiles_sample_rate: float = Field(0.0, alias="SENTRY_PROFILES_SAMPLE_RATE")

    # ──────────────────────────────────────────────────────────────
    # Cost & reliability controls
    # ──────────────────────────────────────────────────────────────
    # Per-(user, org) daily output-token ceiling. 0 disables the cap.
    daily_token_budget: int = Field(0, alias="DAILY_TOKEN_BUDGET")
    # Circuit breaker: after N consecutive provider failures, short-circuit for
    # ``circuit_cooldown_seconds`` instead of hammering a down provider.
    circuit_failure_threshold: int = Field(5, alias="CIRCUIT_FAILURE_THRESHOLD")
    circuit_cooldown_seconds: int = Field(30, alias="CIRCUIT_COOLDOWN_SECONDS")
    # Structured per-turn audit log (actor, tools, model, tokens) in Mongo.
    audit_log_enabled: bool = Field(True, alias="AUDIT_LOG_ENABLED")

    # ──────────────────────────────────────────────────────────────
    # Online web search (Part of the agent toolset)
    # ──────────────────────────────────────────────────────────────
    web_search_enabled: bool = Field(True, alias="WEB_SEARCH_ENABLED")
    # Tavily (keyed, higher quality). Without a key the agent falls back to
    # DuckDuckGo (no key, flakier) when WEB_SEARCH_ENABLED is true.
    tavily_api_key: str | None = Field(None, alias="TAVILY_API_KEY")
    web_search_max_results: int = Field(5, alias="WEB_SEARCH_MAX_RESULTS")

    # ──────────────────────────────────────────────────────────────
    # Hybrid RAG / semantic search (app/rag/). OPTIONAL at every layer —
    # the agent works in pure-agentic mode (live GitHub API) when off.
    # ──────────────────────────────────────────────────────────────
    rag_enabled: bool = Field(True, alias="RAG_ENABLED")
    # Vector backend: chroma (embedded, default) | pgvector | qdrant.
    vector_backend: str = Field("chroma", alias="VECTOR_BACKEND")
    chroma_path: str = Field("./.chroma", alias="CHROMA_PATH")
    pgvector_dsn: str | None = Field(None, alias="PGVECTOR_DSN")
    qdrant_url: str | None = Field(None, alias="QDRANT_URL")
    qdrant_api_key: str | None = Field(None, alias="QDRANT_API_KEY")

    # Embedding providers, routed by content kind. "auto" resolves to the
    # first available provider (Gemini is default since its key is present
    # and it needs no extra dependency). Other options: voyage | openai |
    # local (sentence-transformers) | gemini | none (disables that kind).
    embed_code_provider: str = Field("auto", alias="EMBED_CODE_PROVIDER")
    embed_prose_provider: str = Field("auto", alias="EMBED_PROSE_PROVIDER")
    # text-embedding-004 was retired by Google (404); gemini-embedding-001
    # replaces it and returns 3072-dim vectors (the embedder self-corrects dim).
    gemini_embed_model: str = Field("gemini-embedding-001", alias="GEMINI_EMBED_MODEL")
    voyage_api_key: str | None = Field(None, alias="VOYAGE_API_KEY")
    voyage_code_model: str = Field("voyage-code-3", alias="VOYAGE_CODE_MODEL")
    openai_embed_model: str = Field(
        "text-embedding-3-small", alias="OPENAI_EMBED_MODEL"
    )
    local_code_model: str = Field(
        "jinaai/jina-embeddings-v2-base-code", alias="LOCAL_CODE_MODEL"
    )
    local_prose_model: str = Field("BAAI/bge-small-en-v1.5", alias="LOCAL_PROSE_MODEL")

    # Indexing knobs
    rag_prose_window_days: int = Field(90, alias="RAG_PROSE_WINDOW_DAYS")
    rag_max_file_bytes: int = Field(524_288, alias="RAG_MAX_FILE_BYTES")
    rag_index_interval_min: int = Field(60, alias="RAG_INDEX_INTERVAL_MIN")
    rag_embed_batch: int = Field(64, alias="RAG_EMBED_BATCH")
    rag_retrieval_k: int = Field(8, alias="RAG_RETRIEVAL_K")
    # Per index-tick repo cap so a huge org doesn't stall the scheduler.
    rag_max_repos_per_tick: int = Field(5, alias="RAG_MAX_REPOS_PER_TICK")

    # URLs
    app_base_url: str = Field("https://api.dypol.dev", alias="APP_BASE_URL")
    web_base_url: str = Field("https://www.dypol.dev", alias="WEB_BASE_URL")

    # Session
    session_secret: str = Field(..., alias="SESSION_SECRET")
    session_cookie_name: str = Field("dypol_session", alias="SESSION_COOKIE_NAME")
    session_max_age_days: int = Field(14, alias="SESSION_MAX_AGE_DAYS")

    # Mongo
    mongo_uri: str = Field("mongodb://localhost:27017", alias="MONGO_URI")
    mongo_db: str = Field("dypol", alias="MONGO_DB")

    # App
    app_host: str = Field("0.0.0.0", alias="APP_HOST")
    app_port: int = Field(8000, alias="APP_PORT")
    app_env: str = Field("dev", alias="APP_ENV")
    cors_origins: str = Field("https://www.dypol.dev", alias="CORS_ORIGINS")

    # Cache
    cache_ttl_repos: int = Field(300, alias="CACHE_TTL_REPOS")
    cache_ttl_prs: int = Field(120, alias="CACHE_TTL_PRS")
    cache_ttl_members: int = Field(600, alias="CACHE_TTL_MEMBERS")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def gemini_api_key_list(self) -> list[str]:
        """Every configured Gemini key, primary first, deduped.

        Comments after the value in .env (``KEY=abc  # label``) are stripped by
        the dotenv parser, but stray whitespace/quotes are not — so trim here
        rather than shipping a key with a trailing space to Google.
        """
        raw = [self.gemini_api_key] + [
            getattr(self, f"gemini_api_key_{i}", None) for i in range(1, 9)
        ]
        out: list[str] = []
        seen: set[str] = set()
        for key in raw:
            cleaned = (key or "").strip().strip("\"'")
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                out.append(cleaned)
        return out

    @property
    def provider_order_list(self) -> list[str]:
        """Provider keys in fallback priority order (deduped, lowercased)."""
        seen: set[str] = set()
        out: list[str] = []
        for p in self.agent_provider_order.split(","):
            p = p.strip().lower()
            if p and p not in seen:
                seen.add(p)
                out.append(p)
        return out

    @property
    def is_prod(self) -> bool:
        return self.app_env.lower() in {"prod", "production"}

    @property
    def session_max_age_seconds(self) -> int:
        return self.session_max_age_days * 86400

    @property
    def oauth_redirect_uri(self) -> str:
        return f"{self.app_base_url.rstrip('/')}/auth/callback"

    @property
    def install_url(self) -> str:
        # /select_target always shows the account picker.
        # /installations/new sometimes redirects logged-in users straight
        # to their last-used target, hiding the picker.
        return f"https://github.com/apps/{self.github_app_slug}/installations/select_target"

    def load_private_key(self) -> str:
        """Resolve the App private key from inline env or file path."""
        if self.github_app_private_key:
            return (
                self.github_app_private_key.strip().strip("\"'").replace("\\n", "\n")
            )
        if self.github_app_private_key_path:
            path = Path(self.github_app_private_key_path)
            if not path.is_absolute():
                path = Path.cwd() / path
            return path.read_text()
        raise RuntimeError(
            "Set either GITHUB_APP_PRIVATE_KEY (inline PEM) "
            "or GITHUB_APP_PRIVATE_KEY_PATH (path to .pem file)"
        )

    @model_validator(mode="after")
    def _check_keys(self) -> "Settings":
        if not (self.github_app_private_key or self.github_app_private_key_path):
            raise ValueError(
                "Provide GITHUB_APP_PRIVATE_KEY or GITHUB_APP_PRIVATE_KEY_PATH"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
