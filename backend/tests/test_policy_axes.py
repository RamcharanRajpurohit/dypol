"""The four resource axes as they exist TODAY (FUTURE_PLAN §2.2).

These are characterization tests: they pin the *current* hand-tuned behaviour
so Phase 2's "behaviour-preserving refactor" has something to preserve
against. The plan calls the hand-written baseline the expert control arm the
learned policy must beat — an arm you can't reproduce isn't a baseline.

If one of these fails after a refactor, the refactor changed behaviour.
"""
from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agents import providers
from app.agents.memory import trim_history


# ── Axis 1: model ────────────────────────────────────────────────────
def test_model_chain_pairs_each_provider_with_its_fallback(monkeypatch):
    """Documented shape: [(p, False), (p, True), (q, False), (q, True)] —
    primary model first, then the cheap model, then escalate provider."""
    monkeypatch.setattr(providers, "enabled_providers", lambda: ["gemini", "groq"])
    assert providers.model_chain() == [
        ("gemini", False),
        ("gemini", True),
        ("groq", False),
        ("groq", True),
    ]


def test_model_chain_is_empty_when_no_provider_configured(monkeypatch):
    monkeypatch.setattr(providers, "enabled_providers", lambda: [])
    assert providers.model_chain() == []


def test_role_policy_is_a_static_table_that_ignores_the_query():
    """§2.2's central finding: model choice is a role→tier lookup with no
    query input at all. Phase 3 replaces exactly this."""
    policy = providers._ROLE_POLICY
    assert policy["router"][1] is True  # cheap
    assert policy["analyst"][1] is False  # strong
    assert policy["web"][1] is True  # cheap
    assert policy["synth"][1] is False  # strong


def test_gemini_counts_as_enabled_from_any_pool_key(monkeypatch):
    """Keys may be supplied only as GEMINI_API_KEY_1.. with no base key."""
    monkeypatch.setattr(providers, "model_chain", lambda: [])
    from app.core import keypool

    monkeypatch.setattr(keypool, "gemini_keys", lambda: ["k1"])
    monkeypatch.setattr(
        providers.get_settings(), "agent_provider_order", "gemini", raising=False
    )
    assert "gemini" in providers.enabled_providers()


# ── Quota detection (drives the reactive model swap) ─────────────────
@pytest.mark.parametrize(
    "message",
    [
        "429 Too Many Requests",
        "RESOURCE_EXHAUSTED: quota exceeded",
        "rate_limit_exceeded",
        "You have hit the rate limit",
    ],
)
def test_quota_errors_are_recognised(message):
    assert providers.is_quota_error(RuntimeError(message)) is True


def test_ordinary_errors_are_not_mistaken_for_quota():
    assert providers.is_quota_error(ValueError("bad schema")) is False


def test_quota_detected_by_exception_type_name():
    class ResourceExhausted(Exception):  # noqa: N818 — mirrors google-api-core's real name
        pass

    assert providers.is_quota_error(ResourceExhausted("nothing useful here")) is True


# ── Axis 3: memory depth ─────────────────────────────────────────────
def _history(turns: int) -> list:
    msgs: list = [SystemMessage(content="system")]
    for i in range(turns):
        msgs.append(HumanMessage(content=f"question {i} " + "padding " * 50))
        msgs.append(AIMessage(content=f"answer {i} " + "padding " * 50))
    return msgs


def test_trim_history_keeps_the_most_recent_turns():
    msgs = _history(20)
    kept = trim_history(msgs, max_tokens=500)
    assert len(kept) < len(msgs), "nothing was trimmed — budget had no effect"
    # The newest exchange must survive; dropping it would drop the question.
    assert kept[-1].content == msgs[-1].content


def test_trim_history_is_a_noop_under_a_generous_budget():
    msgs = _history(3)
    assert len(trim_history(msgs, max_tokens=1_000_000)) == len(msgs)


def test_trim_history_never_returns_empty():
    """Robustness contract in the docstring: a trimming hiccup must never
    drop the user's actual question."""
    assert trim_history(_history(20), max_tokens=1) != []


def test_trim_history_tolerates_an_empty_history():
    assert trim_history([], max_tokens=1000) == []
