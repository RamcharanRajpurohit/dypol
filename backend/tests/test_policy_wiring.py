"""The decision reaches the real machinery — and the default changes nothing.

These are the Phase-2 exit criterion in test form: with the default
``role_table`` policy, every request DyPol builds is identical to before the
policy layer existed; with another policy, each axis lands where it should.
No network: model construction and tool building are stubbed at the seams.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from app.agents import graph as graph_mod
from app.agents import providers
from app.agents.tracing import TraceCollector
from app.policy.decision import EffortLevel, PolicyDecision, RetrievalDepth, ToolScope


# ── build_model: effort → constructor kwargs ─────────────────────────
class _FakeModel:
    def __init__(self, name: str, kwargs: dict[str, Any]):
        self.name = name
        self.kwargs = kwargs
        self.bound: dict[str, Any] | None = None

    def bind_tools(self, tools, **kw):
        self.bound = {"tools": tools, **kw}
        return self


@pytest.fixture
def captured(monkeypatch):
    """Capture what build_model hands to init_chat_model."""
    import langchain.chat_models as lc

    calls: list[_FakeModel] = []

    def fake_init(model_name, **kwargs):
        m = _FakeModel(model_name, kwargs)
        calls.append(m)
        return m

    monkeypatch.setattr(lc, "init_chat_model", fake_init)
    monkeypatch.setattr(providers, "_api_key_for", lambda provider, spec: "test-key")
    return calls


def _set_model(monkeypatch, attr: str, value: str):
    monkeypatch.setattr(providers.get_settings(), attr, value, raising=False)


def test_build_model_without_effort_is_unchanged(captured, monkeypatch):
    _set_model(monkeypatch, "gemini_model", "gemini-2.5-flash")
    providers.build_model("gemini")
    providers.build_model("gemini", effort=EffortLevel.DEFAULT)
    first, second = captured
    assert first.kwargs == second.kwargs
    assert "thinking_budget" not in first.kwargs


def test_build_model_applies_gemini_thinking_budget(captured, monkeypatch):
    _set_model(monkeypatch, "gemini_model", "gemini-2.5-flash")
    providers.build_model("gemini", effort=EffortLevel.NONE)
    assert captured[0].kwargs["thinking_budget"] == 0
    assert "max_output_tokens" in captured[0].kwargs


def test_build_model_applies_openai_reasoning_effort(captured, monkeypatch):
    _set_model(monkeypatch, "openai_model", "gpt-5-mini")
    providers.build_model("openai", effort=EffortLevel.HIGH)
    assert captured[0].kwargs["reasoning_effort"] == "high"


def test_build_model_skips_effort_for_models_without_a_knob(captured, monkeypatch):
    _set_model(monkeypatch, "openai_model", "gpt-4o")
    providers.build_model("openai", effort=EffortLevel.HIGH)
    assert "reasoning_effort" not in captured[0].kwargs


def test_anthropic_thinking_relaxes_a_forced_tool_choice(captured, monkeypatch):
    """Anthropic rejects tool_choice='any' while extended thinking is on."""
    _set_model(monkeypatch, "anthropic_model", "claude-sonnet-4-6")
    tools = [SimpleNamespace(name="github_get")]
    providers.build_model("anthropic", tools=tools, tool_choice="any", effort=EffortLevel.HIGH)
    m = captured[0]
    assert m.kwargs["thinking"] == {"type": "adaptive"}
    assert m.kwargs["temperature"] == 1.0
    assert m.bound["tool_choice"] == "auto"


def test_forced_tool_choice_kept_when_no_thinking(captured, monkeypatch):
    _set_model(monkeypatch, "anthropic_model", "claude-sonnet-4-6")
    tools = [SimpleNamespace(name="github_get")]
    providers.build_model("anthropic", tools=tools, tool_choice="any")
    assert captured[0].bound["tool_choice"] == "any"


# ── TraceCollector records the decision ──────────────────────────────
def test_collector_records_decision_and_policy_in_summary():
    c = TraceCollector()
    assert c.decision() is None
    assert c.usage_summary()["policy"] is None
    c.record_decision(PolicyDecision(policy="heuristic_router"))
    assert c.decision()["policy"] == "heuristic_router"
    assert c.usage_summary()["policy"] == "heuristic_router"


def test_collector_survives_a_bad_decision_object():
    c = TraceCollector()
    c.record_decision(object())
    assert c.decision() is None


# ── _build_turn applies scope + records the decision ─────────────────
@pytest.fixture
def turn_seams(monkeypatch):
    """Stub the tool builders and the graph compiler; record what they got."""
    seen: dict[str, Any] = {"delegates_built": 0}

    def fake_build_tools(install, *, names=None, extra_tools=None):
        seen["install"] = install
        core = [SimpleNamespace(name=n) for n in ("github_get", "web_search", "semantic_search")]
        return core + list(extra_tools or [])

    def fake_delegates(install, *, budget, trace):
        seen["delegates_built"] += 1
        return [SimpleNamespace(name="delegate_code_analyst")]

    def fake_graph(tools, install, collector=None, decision=None):
        seen["tools"] = [t.name for t in tools]
        seen["decision"] = decision
        return SimpleNamespace()

    import app.agents.registry as agent_registry
    import app.agents.tools as agent_tools

    monkeypatch.setattr(agent_tools, "build_tools", fake_build_tools)
    monkeypatch.setattr(agent_registry, "build_delegate_tools", fake_delegates)
    monkeypatch.setattr(graph_mod, "build_agent_graph", fake_graph)
    return seen


def _use_policy(monkeypatch, name: str):
    from app.policy import registry

    monkeypatch.setattr(registry, "_configured_name", lambda: name)


def test_default_policy_builds_the_same_turn_as_before(turn_seams, monkeypatch):
    _use_policy(monkeypatch, "role_table")
    _, collector, _ = graph_mod._build_turn({"install_id": 1}, [], "why did CI fail?", None)
    assert turn_seams["delegates_built"] == 1
    assert turn_seams["tools"] == [
        "github_get",
        "web_search",
        "semantic_search",
        "delegate_code_analyst",
    ]
    assert turn_seams["decision"].policy == "role_table"
    assert turn_seams["install"]["_policy_retrieval_k"] is None
    assert collector.decision()["policy"] == "role_table"


def test_core_scope_skips_delegates_and_extended_tools(turn_seams, monkeypatch):
    _use_policy(monkeypatch, "always_cheap")
    graph_mod._build_turn({"install_id": 1}, [], "why did CI fail?", None)
    assert turn_seams["delegates_built"] == 0
    assert turn_seams["tools"] == ["github_get"]
    assert turn_seams["decision"].tool_scope is ToolScope.CORE
    assert turn_seams["install"]["_policy_retrieval_k"] == 4


def test_smalltalk_router_turn_unbinds_semantic_search(turn_seams, monkeypatch):
    _use_policy(monkeypatch, "heuristic_router")
    graph_mod._build_turn({"install_id": 1}, [], "hi", None)
    assert turn_seams["decision"].retrieval is RetrievalDepth.NONE
    assert "semantic_search" not in turn_seams["tools"]


def test_build_turn_does_not_mutate_the_callers_install(turn_seams, monkeypatch):
    _use_policy(monkeypatch, "always_cheap")
    install = {"install_id": 1}
    graph_mod._build_turn(install, [], "q", None)
    assert install == {"install_id": 1}


# ── semantic_search honours the per-turn retrieval default ───────────
def _search_handler(monkeypatch, captured_k: list):
    import app.rag as rag_pkg
    import app.rag.retriever as retriever
    import app.rag.tenant as tenant

    monkeypatch.setattr(rag_pkg, "is_rag_enabled", lambda: True)
    monkeypatch.setattr(tenant, "tenant_id_for", lambda ws: 7)

    async def fake_hybrid(tenant_id, query, *, kind="any", repo=None, k=None, **_):
        captured_k.append(k)
        return []

    monkeypatch.setattr(retriever, "hybrid_search", fake_hybrid)
    return retriever.semantic_search_handler_factory


def test_retrieval_k_precedence(monkeypatch):
    ks: list = []
    factory = _search_handler(monkeypatch, ks)
    default_k = providers.get_settings().rag_retrieval_k

    asyncio.run(factory({"install_id": 1})("q"))  # settings
    asyncio.run(factory({"install_id": 1, "_policy_retrieval_k": 4})("q"))  # policy
    asyncio.run(factory({"install_id": 1, "_policy_retrieval_k": 4})("q", k=9))  # model
    assert ks == [default_k, 4, 9]
