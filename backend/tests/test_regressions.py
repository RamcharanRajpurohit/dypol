"""Regression tests for bugs that actually shipped.

Each test here corresponds to a defect found in this codebase, so the suite
has teeth beyond happy-path coverage. Comments name the failure mode — a test
whose reason for existing is forgotten gets deleted in the next refactor.
"""
from __future__ import annotations

import pytest

from app.agents.graph import _looks_like_tool_payload
from app.core import keypool
from app.rag.tenant import tenant_for
from app.services.activity import _from_public_event, _summarize
from app.services.repos import _status_for, repo_scan_cap


# ── The model echoed a tool payload as its answer ────────────────────
def test_serialized_function_response_is_rejected_as_an_answer():
    """Gemini emitted its own tool result as text; every emptiness check
    passed because a JSON blob is a non-empty string, so it was persisted
    and shown to the user."""
    payload = '{"github_search_response": {"output": "{\\"total_count\\": 135, \\"items\\": ['
    assert _looks_like_tool_payload(payload) is True


@pytest.mark.parametrize(
    "text",
    [
        '{"total_count": 5, "items": []}',
        '[{"name": "repo1"}, {"name": "repo2"}]',
    ],
)
def test_bare_json_documents_are_rejected(text):
    assert _looks_like_tool_payload(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "Found 12 open PRs. The three oldest are…",
        'The config uses {"a": 1} internally.',
        '```json\n{"a": 1}\n```',  # a fenced block is legitimate prose
        "",
    ],
)
def test_real_answers_are_not_rejected(text):
    assert _looks_like_tool_payload(text) is False


# ── Every repo reported 0 open PRs ───────────────────────────────────
def test_status_reflects_open_pr_count():
    """list_org_repos never passed open_prs, so _status_for always saw 0 and
    every row collapsed to 'neutral' — the hot/stuck signal was dead."""
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    assert _status_for(12, now) == "hot"
    assert _status_for(3, now - timedelta(days=30)) == "stuck"
    assert _status_for(3, now) == "ok"
    assert _status_for(0, now) == "neutral"


def test_repo_scan_cap_is_smaller_without_an_installation():
    """A public workspace shares one 60 req/hr anonymous budget; scanning an
    install-sized slice would spend the whole hour on one page load."""
    install = repo_scan_cap(12345, install_cap=30)
    anonymous = repo_scan_cap(None, install_cap=30)
    assert install == 30
    assert anonymous < install


# ── Anonymous event payloads are slimmed ─────────────────────────────
def test_push_without_a_commit_count_omits_it():
    """The anonymous timeline ships no commit list; the old code rendered
    '(0 commits)' for every push."""
    line = _summarize("push", {"ref": "refs/heads/master", "commits": None}, None)
    assert "commits" not in line
    assert line == "pushed to master"


def test_push_with_a_commit_count_still_shows_it():
    assert _summarize("push", {"ref": "refs/heads/main", "commits": 3}, None) == (
        "pushed to main (3 commits)"
    )


def test_pr_without_a_title_omits_the_dash():
    """Anonymous PullRequestEvent carries no title; the old code rendered
    'PR #27 — None'."""
    line = _summarize("pull_request", {"number": 27, "title": None}, "closed")
    assert "None" not in line
    assert line == "PR #27 (closed)"


def test_public_event_maps_to_a_feed_row():
    event = _from_public_event(
        {
            "id": "123",
            "type": "PushEvent",
            "actor": {"login": "octocat", "avatar_url": "https://x/a.png"},
            "repo": {"name": "acme/widgets"},
            "payload": {"ref": "refs/heads/main", "size": 2},
            "created_at": "2026-07-27T14:03:11Z",
        }
    )
    assert event is not None
    assert event.actor == "octocat"
    assert event.repo == "acme/widgets"
    assert event.summary == "pushed to main (2 commits)"


def test_unknown_event_types_are_dropped():
    assert _from_public_event({"type": "GollumEvent", "id": "1"}) is None


# ── RAG tenancy ──────────────────────────────────────────────────────
def test_install_tenant_id_is_unchanged():
    """Changing it would orphan every existing index."""
    t = tenant_for({"install_id": 131110073, "account_login": "acme"})
    assert t is not None and t.id == 131110073 and t.is_public is False


def test_public_tenants_share_one_namespace_per_account():
    """Two users tracking the same public org must not embed it twice."""
    a = tenant_for({"account_login": "kubernetes", "account_id": 13629408, "owner_user_id": 1})
    b = tenant_for({"account_login": "kubernetes", "account_id": 13629408, "owner_user_id": 2})
    assert a is not None and b is not None
    assert a.id == b.id


def test_public_and_install_namespaces_cannot_collide():
    pub = tenant_for({"account_login": "k8s", "account_id": 555, "owner_user_id": 1})
    ins = tenant_for({"install_id": 555, "account_login": "acme"})
    assert pub is not None and ins is not None
    assert pub.id != ins.id


def test_public_workspace_without_an_account_id_is_skipped():
    """No stable namespace ⇒ skip rather than risk a collision."""
    assert tenant_for({"account_login": "old", "owner_user_id": 1}) is None


# ── Gemini key rotation ──────────────────────────────────────────────
def test_keys_rotate_and_wrap(monkeypatch):
    monkeypatch.setattr(keypool, "gemini_keys", lambda: ["a", "b", "c"])
    keypool._snapshot = ()  # force a fresh cycle
    got = [keypool.next_gemini_key() for _ in range(7)]
    assert got == ["a", "b", "c", "a", "b", "c", "a"]


def test_no_keys_returns_none(monkeypatch):
    monkeypatch.setattr(keypool, "gemini_keys", lambda: [])
    assert keypool.next_gemini_key() is None


def test_rotation_resets_when_the_key_list_changes(monkeypatch):
    monkeypatch.setattr(keypool, "gemini_keys", lambda: ["a", "b"])
    keypool._snapshot = ()
    keypool.next_gemini_key()
    monkeypatch.setattr(keypool, "gemini_keys", lambda: ["x"])
    assert keypool.next_gemini_key() == "x"


def test_pool_description_never_leaks_a_whole_key(monkeypatch):
    secret = "AIzaSyVERYSECRETKEYVALUE123456"
    monkeypatch.setattr(keypool, "gemini_keys", lambda: [secret])
    described = keypool.describe_pool()
    assert secret not in described
    assert described.endswith("…123456")


# ── Truncated sub-agent results must be marked, not laundered ────────
def test_partial_subagent_result_is_marked():
    """A code-analysis sub-agent spent all 6 of its turns walking directories,
    hit the cap, and reported 'could not read' for a path that was readable —
    and the orchestrator relayed that as fact. The fix is that a truncated
    result must be distinguishable from a completed one."""
    from app.agents.base import _mark_truncated
    from app.agents.budget import DelegationBudget

    marked = _mark_truncated("I was unable to locate the auth module.", DelegationBudget())
    assert marked.startswith("[PARTIAL RESULT")
    assert "NOT CHECKED" in marked
    assert "I was unable to locate the auth module." in marked


def test_subagent_turn_cap_allows_reading_code_not_just_navigating():
    """Six turns was consumed by directory navigation alone (contents → src →
    src/lib → src/app → src/app/api) before a single file was opened."""
    from app.agents.budget import MAX_TOOL_TURNS, DelegationBudget

    assert MAX_TOOL_TURNS >= 10, "too tight to open a file after navigating to it"
    # The shared pool must not starve a sub-agent of the turns it was granted.
    assert DelegationBudget().global_tool_cap >= MAX_TOOL_TURNS * 2


def test_zero_evidence_delegation_is_flagged_unverified():
    """Measured failure: on identical inputs a sub-agent read 8 route files on
    one run and ZERO on the next, returning the same confident 'no problems
    found' both times. Text can't distinguish those — the evidence count can."""
    from app.agents.tracing import TraceCollector

    t = TraceCollector()
    t.record("delegate_code_analyst", {}, "delegating", 0)
    before = len(t.as_chat_tool_calls())
    # sub-agent that inspected nothing
    rows = t.as_chat_tool_calls()[before:]
    evidence = [r for r in rows if r["name"].startswith("code_analyst→")]
    assert evidence == [], "no sub-agent tool calls were recorded"

    # ...and one that actually read files
    t.record("github_get", {}, "path=a.ts", 5, label="code_analyst")
    t.record("github_get", {}, "path=b.ts", 5, label="code_analyst")
    rows = t.as_chat_tool_calls()[before:]
    evidence = [r for r in rows if r["name"].startswith("code_analyst→")]
    assert len(evidence) == 2


# ── Sub-agent prompts advertise a superset of what's bound ───────────
def test_bound_tools_block_states_the_real_bindings():
    """`registry._spec_available` admits a sub-agent when ANY of its declared
    TOOL_NAMES exist, so code_analyst runs whenever github_get does — while its
    static prompt still says 'Try semantic_search first'. With RAG off that is
    an unknown_tool error and a wasted step of a tight budget."""
    from app.agents.subagent_prompts import bound_tools_block

    block = bound_tools_block({"github_get", "python_exec"})
    assert "github_get" in block and "python_exec" in block
    assert "semantic_search" not in block
    assert "overrides" in block.lower()


def test_bound_tools_block_handles_an_empty_binding():
    from app.agents.subagent_prompts import bound_tools_block

    assert "(none)" in bound_tools_block(set())


def test_subagents_pass_the_augmented_prompt_not_the_static_one():
    """Regression: the augmented prompt was built into a local variable and
    then the static PROMPT was passed to the loop anyway."""
    import inspect

    from app.agents.subagents import code_analyst, pr_activity_analyst, web_researcher

    for mod in (code_analyst, pr_activity_analyst, web_researcher):
        src = inspect.getsource(mod.run)
        assert "system_prompt=system_prompt" in src, mod.__name__
        assert "system_prompt=PROMPT," not in src, mod.__name__


# ── The fallback chain was illusory ──────────────────────────────────
def test_too_large_is_not_mistaken_for_quota():
    """Groq free tier caps at 8K TPM while a real turn carries 12-25K input
    tokens, so Groq 413s on every production turn. Waiting doesn't help and
    neither does its cheaper fallback model — it shares the ceiling."""
    from app.agents.providers import is_context_error, is_quota_error

    err = Exception("Error code: 413 - Request too large for model `openai/gpt-oss-120b`")
    assert is_context_error(err) is True
    # It must NOT be treated as transient/quota, which would imply retrying.
    assert is_quota_error(Exception("context length exceeded")) is False


def test_ordinary_quota_error_is_not_a_context_error():
    from app.agents.providers import is_context_error

    assert is_context_error(Exception("RESOURCE_EXHAUSTED: quota")) is False


def test_nudge_does_not_point_at_a_blocked_path():
    """The stall nudge told the model to call /user/repos, which the read-only
    allowlist rejects with path_not_allowed — the agent followed its own
    instruction into a dead end and burned the recovery turn."""
    import inspect

    from app.agents import graph
    from app.services.chat_tools import _path_allowed

    assert _path_allowed("/user/repos") is False, "premise changed"
    src = inspect.getsource(graph.build_agent_graph)
    nudge = src[src.find("You stopped without answering") :][:600]
    assert "/installation/repositories" in nudge
    # It may name the path only to warn against it, never as the thing to call.
    assert "NOT " in nudge or "/user/repos" not in nudge


def test_payload_guard_catches_an_embedded_dump_not_just_a_leading_one():
    """Asked to justify its answer, the model apologised in prose and then
    pasted ~2 KB of escaped github_get_response JSON. The original guard only
    checked whether the text STARTED with '{', so it passed straight through."""
    from app.agents.graph import _looks_like_tool_payload

    embedded = (
        "You are correct, my apologies. The endpoint used was "
        '/installation/repositories. The output was:```json\n'
        '{"github_get_response": {"output": "{\\"total_count\\": 29, ...'
    )
    assert _looks_like_tool_payload(embedded) is True
    # Prose that merely mentions a tool must still pass.
    assert _looks_like_tool_payload(
        "I used github_get on /installation/repositories and found 29 repos."
    ) is False


def test_installation_repositories_is_slimmed_not_truncated():
    """The wrapper shape {"total_count", "repositories"} fell through every
    slimming rule and hit the 24 KB cap — 170 KB collapsed to a `_preview`
    string, so the model guessed the repo count and got it wrong confidently."""
    from app.services.chat_tools import _slim_rest_list

    raw = {
        "total_count": 3,
        "repository_selection": "all",
        "repositories": [
            {"name": "a", "full_name": "o/a", "private": True, "stargazers_count": 1},
            {"name": "b", "full_name": "o/b", "private": False, "stargazers_count": 2},
            {"name": "c", "full_name": "o/c", "private": False, "stargazers_count": 3},
        ],
    }
    out = _slim_rest_list("/installation/repositories", raw)
    assert out["total_count"] == 3
    assert out["_private_count"] == 1
    assert out["_public_count"] == 2
    assert len(out["repositories"]) == 3
