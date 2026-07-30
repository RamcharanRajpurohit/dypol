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
