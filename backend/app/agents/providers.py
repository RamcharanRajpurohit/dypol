"""Provider layer — provider registry, model factory, and fallback chain.

The agent (``app/agents/graph.py``) is provider-agnostic: it talks to ANY
configured LLM (Claude / OpenAI / Gemini / Groq) through LangChain's
``init_chat_model``. This module is the single place that:

  * maps our short provider keys → the ``init_chat_model`` provider strings,
  * decides which providers are *enabled* (api key present, in the order
    configured by ``AGENT_PROVIDER_ORDER``),
  * builds a bound ``BaseChatModel`` for a given provider (with the right
    per-provider max-tokens kwarg quirk handled), and
  * expresses the cross-provider + quota-swap fallback as one flat
    ``model_chain()`` the graph walks on error.

Everything heavy (``init_chat_model`` and the per-provider LangChain
integration packages) is imported lazily inside functions so a missing
optional integration never breaks boot.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.config import get_settings

if TYPE_CHECKING:  # avoid importing langchain at module top
    from langchain_core.language_models import BaseChatModel


# ──────────────────────────────────────────────────────────────────
# Provider registry — short key → settings attrs + init_chat_model provider.
#
# ``lc_provider`` is the ``model_provider`` string ``init_chat_model`` expects
# to pick the right LangChain integration package:
#   groq      → langchain-groq
#   gemini    → langchain-google-genai  ("google_genai")
#   anthropic → langchain-anthropic
#   openai    → langchain-openai
# ──────────────────────────────────────────────────────────────────
PROVIDER_REGISTRY: dict[str, dict[str, str]] = {
    "groq": {
        "api_key_attr": "groq_api_key",
        "model_attr": "groq_model",
        "fallback_model_attr": "groq_fallback_model",
        "lc_provider": "groq",
    },
    "gemini": {
        "api_key_attr": "gemini_api_key",
        "model_attr": "gemini_model",
        "fallback_model_attr": "gemini_fallback_model",
        "lc_provider": "google_genai",
    },
    "anthropic": {
        "api_key_attr": "anthropic_api_key",
        "model_attr": "anthropic_model",
        "fallback_model_attr": "anthropic_fallback_model",
        "lc_provider": "anthropic",
    },
    "openai": {
        "api_key_attr": "openai_api_key",
        "model_attr": "openai_model",
        "fallback_model_attr": "openai_fallback_model",
        "lc_provider": "openai",
    },
}


def enabled_providers() -> list[str]:
    """Provider keys, in configured fallback order, whose API key is set.

    Reads ``settings.provider_order_list`` (deduped, lowercased) and keeps
    only providers we know about *and* that have a truthy API key.
    """
    s = get_settings()
    out: list[str] = []
    for p in s.provider_order_list:
        spec = PROVIDER_REGISTRY.get(p)
        if spec is None:
            continue
        # Gemini counts as configured if ANY key in the pool is set, so a
        # deployment that only fills GEMINI_API_KEY_1.. still enables it.
        if p == "gemini":
            from app.core.keypool import gemini_keys

            if gemini_keys():
                out.append(p)
            continue
        if getattr(s, spec["api_key_attr"], None):
            out.append(p)
    return out


def is_agent_enabled() -> bool:
    """True if at least one provider is configured (has an API key)."""
    return bool(enabled_providers())


# ──────────────────────────────────────────────────────────────────
# Per-provider max-tokens adapter.
#
# anthropic / openai / groq integrations accept ``max_tokens``; the
# google_genai integration uses ``max_output_tokens`` instead. Centralised
# here so build_model() stays clean.
# ──────────────────────────────────────────────────────────────────
def _max_tokens_kwargs(lc_provider: str, max_tokens: int) -> dict[str, int]:
    if lc_provider == "google_genai":
        return {"max_output_tokens": max_tokens}
    return {"max_tokens": max_tokens}


def _api_key_for(provider: str, spec: dict[str, str]) -> Any:
    """The API key to build this model with.

    Gemini rotates across every configured key (GEMINI_API_KEY plus
    GEMINI_API_KEY_1..8) so separate projects' quotas are all used, and a
    quota-triggered retry lands on a different key. Other providers just read
    their single configured key.
    """
    if provider == "gemini":
        from app.core.keypool import next_gemini_key

        return next_gemini_key()
    return getattr(get_settings(), spec["api_key_attr"], None)


def build_model(
    provider: str,
    *,
    use_fallback: bool = False,
    tools: list[Any] | None = None,
    tool_choice: str | None = None,
) -> BaseChatModel:
    """Construct a bound ``BaseChatModel`` for ``provider``.

    ``use_fallback`` selects the provider's lighter/cheaper fallback model
    (used by the quota-swap path). ``tools``, when given, are bound via
    ``.bind_tools(tools)`` so the model can emit tool calls.

    ``tool_choice`` — when tools are bound, controls whether the model is FORCED
    to call a tool. ``"any"`` forces a tool call (critical for Gemini 2.5-flash,
    which otherwise replies with text instead of calling tools); ``"auto"`` lets
    it choose (used for the final synthesis turn). Provider-aware: not all
    providers accept the same value, so we degrade to a plain bind on error.
    """
    spec = PROVIDER_REGISTRY.get(provider)
    if spec is None:
        raise ValueError(f"unknown provider {provider!r}")

    s = get_settings()
    model_name = getattr(s, spec["fallback_model_attr" if use_fallback else "model_attr"])
    api_key = _api_key_for(provider, spec)
    lc_provider = spec["lc_provider"]

    # Lazy import — keeps boot independent of the langchain integration packages.
    from langchain.chat_models import init_chat_model

    kwargs: dict[str, Any] = {
        "model_provider": lc_provider,
        "temperature": s.agent_temperature,
        "api_key": api_key,
        **_max_tokens_kwargs(lc_provider, s.agent_max_tokens),
    }
    model = init_chat_model(model_name, **kwargs)
    if tools:
        if tool_choice is not None:
            try:
                return model.bind_tools(tools, tool_choice=tool_choice)
            except Exception:
                pass  # provider doesn't accept tool_choice → plain bind
        model = model.bind_tools(tools)
    return model


# Sub-agent role → (settings override attr, default-to-cheap-model?). The
# override attr holds an optional "provider:model" string; when unset the role
# falls back to the first enabled provider's primary (strong) or fallback
# (cheap) model per the bool. Keeps cheap roles (router/web) on the cheap model
# and deep-analysis roles (analyst/synth) on the strong one — see the plan.
_ROLE_POLICY: dict[str, tuple[str, bool]] = {
    "router": ("agent_router_model", True),
    "analyst": ("agent_analyst_model", False),
    "web": ("agent_web_model", True),
    "synth": ("agent_synth_model", False),
}


def model_for_spec(
    spec: str | None = None,
    *,
    role: str | None = None,
    default_provider: str | None = None,
    default_fallback: bool = False,
    use_fallback: bool | None = None,
    tools: list[Any] | None = None,
) -> BaseChatModel:
    """Resolve a per-role / per-spec model.

    Two ways to call it:
      * ``model_for_spec(role="analyst")`` — sub-agents use this. The role maps
        (via ``_ROLE_POLICY``) to an optional ``settings.agent_*_model`` override
        ("provider:model") and a default cheap/strong policy.
      * ``model_for_spec("groq:openai/gpt-oss-20b")`` — explicit override string.

    ``use_fallback`` (when given) overrides the role's default cheap/strong
    choice — e.g. ``role="web", use_fallback=True`` forces the cheap model.
    """
    # Role form: resolve the override string + default fallback policy.
    if role is not None and spec is None:
        attr, role_default_fallback = _ROLE_POLICY.get(role, (None, default_fallback))
        if attr is not None:
            spec = getattr(get_settings(), attr, None)
        if use_fallback is None:
            use_fallback = role_default_fallback

    if use_fallback is not None:
        default_fallback = use_fallback

    if spec:
        provider_key, _, model_name = spec.partition(":")
        provider_key = provider_key.strip().lower()
        model_name = model_name.strip()
        reg = PROVIDER_REGISTRY.get(provider_key)
        if reg is not None and model_name:
            s = get_settings()
            lc_provider = reg["lc_provider"]
            from langchain.chat_models import init_chat_model

            kwargs: dict[str, Any] = {
                "model_provider": lc_provider,
                "temperature": s.agent_temperature,
                "api_key": _api_key_for(provider_key, reg),
                **_max_tokens_kwargs(lc_provider, s.agent_max_tokens),
            }
            model = init_chat_model(model_name, **kwargs)
            if tools:
                model = model.bind_tools(tools)
            return model
        # Malformed / unknown-provider spec → fall through to the default.

    if default_provider is None:
        enabled = enabled_providers()
        if not enabled:
            raise RuntimeError(
                "No LLM provider configured (set an API key for one of "
                f"{list(PROVIDER_REGISTRY)})"
            )
        default_provider = enabled[0]
    return build_model(default_provider, use_fallback=default_fallback, tools=tools)


def model_chain() -> list[tuple[str, bool]]:
    """Flat fallback chain of ``(provider, use_fallback)`` steps.

    For each enabled provider we yield the primary model first, then its
    fallback (cheaper) model — re-expressing today's behaviour where a quota
    hit first swaps to the lighter model on the same provider, then escalates
    to the next provider. Walked in order by the agent node on any quota /
    hard error.

    Example with order ["gemini", "groq"]:
        [("gemini", False), ("gemini", True), ("groq", False), ("groq", True)]
    """
    chain: list[tuple[str, bool]] = []
    for p in enabled_providers():
        chain.append((p, False))
        chain.append((p, True))
    return chain


# Exception class names that unambiguously signal a rate-limit / quota issue
# across the provider SDKs we use.
_QUOTA_EXC_NAMES = {
    "RateLimitError",  # openai, anthropic, groq SDKs
    "ResourceExhausted",  # google api core
    "ResourceExhaustedError",
}

_QUOTA_SUBSTRINGS = (
    "rate_limit_exceeded",
    "rate limit",
    "429",
    "quota",
    "too many requests",
    "resource_exhausted",
)


# A request the provider structurally cannot accept — the payload exceeds its
# context or per-minute token ceiling. Distinct from a quota error: waiting
# does not help, and neither does the provider's cheaper fallback model, which
# shares the same ceiling.
_TOO_LARGE_SUBSTRINGS = (
    "request too large",
    "request_too_large",
    "413",
    "context length",
    "context_length_exceeded",
    "maximum context",
    "too many tokens",
)


def is_context_error(exc: BaseException) -> bool:
    """True if ``exc`` means "this payload is too big for this provider".

    Measured: Groq's free tier caps `openai/gpt-oss-120b` at 8K tokens/min,
    while a real agent turn here carries 12–25K input tokens (system prompt +
    tool schemas + accumulated tool results). Groq answers a 50-token probe and
    413s on a 12K one — so it can never serve a production turn, and its
    fallback model shares the ceiling. Detecting this lets the chain skip the
    whole provider instead of spending two calls proving it twice.
    """
    msg = str(exc).lower()
    return any(sub in msg for sub in _TOO_LARGE_SUBSTRINGS)


def is_quota_error(exc: BaseException) -> bool:
    """True if ``exc`` looks like a rate-limit / quota / resource-exhausted
    response from any provider — by message substring OR exception type name."""
    if type(exc).__name__ in _QUOTA_EXC_NAMES:
        return True
    msg = str(exc).lower()
    return any(sub in msg for sub in _QUOTA_SUBSTRINGS)
