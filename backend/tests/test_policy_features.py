"""Difficulty featurisation — cheap, deterministic, never raises."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.policy.features import FEATURE_NAMES, TurnFeatures, featurize


def test_vector_matches_names():
    f = featurize("how many PRs merged last week?")
    assert len(f.as_vector()) == len(FEATURE_NAMES)
    assert list(f.as_dict()) == FEATURE_NAMES


def test_empty_input_is_all_zero_and_other():
    f = featurize("")
    assert f.query_chars == 0
    assert f.question_type == "other"


def test_none_inputs_do_not_raise():
    f = featurize(None, None, None)  # type: ignore[arg-type]
    assert isinstance(f, TurnFeatures)


@pytest.mark.parametrize(
    ("question", "qtype"),
    [
        ("How many PRs were merged last week?", "metric"),
        ("Who are the most active contributors this month?", "metric"),
        ("Why did the auth refactor break billing?", "code"),
        ("Explain how the retry function works in the client module", "code"),
        ("What changed in the latest Next.js release notes?", "web"),
        ("hi", "smalltalk"),
        ("thanks!", "smalltalk"),
        ("banana", "other"),
    ],
)
def test_question_type(question, qtype):
    assert featurize(question).question_type == qtype


def test_long_question_starting_with_hi_is_not_smalltalk():
    f = featurize("hi, why does the webhook handler drop events when the queue is full?")
    assert f.question_type == "code"


def test_smalltalk_word_match_is_whole_word():
    # "this" contains "hi" but must not trigger smalltalk.
    assert featurize("this").type_smalltalk == 0.0


def test_code_signals():
    f = featurize("Why does `parse_config` in backend/app/core/config.py raise on empty env?")
    assert f.has_code == 1.0
    assert f.file_paths >= 1
    assert f.identifiers >= 1


def test_pr_and_repo_refs_and_urls():
    f = featurize("Compare #42 and PR 57 in acme/api, see https://github.com/acme/api/pull/57")
    assert f.pr_refs == 2
    assert f.urls == 1
    # The URL is stripped before repo matching so it isn't double-counted.
    assert f.repo_refs >= 1


def test_history_features_from_mongo_dicts():
    prior = [
        {"role": "user", "content": "how many PRs merged last week in api"},
        {"role": "assistant", "content": "12 PRs were merged."},
    ]
    f = featurize("and how many merged in api the week before?", prior)
    assert f.history_turns == 1
    assert f.history_chars > 0
    assert f.topical_continuity > 0.2


def test_history_features_from_objects_and_multipart_content():
    prior = [
        SimpleNamespace(role="user", content=[{"type": "text", "text": "deploy failures in web"}]),
        SimpleNamespace(type="ai", content="three failures"),
    ]
    f = featurize("unrelated: who owns billing?", prior)
    assert f.history_turns == 1
    assert f.topical_continuity < 0.2


def test_fresh_conversation_has_zero_continuity():
    assert featurize("anything at all").topical_continuity == 0.0


def test_workspace_size_from_count_or_list():
    assert featurize("q", install={"repo_count": 7}).workspace_repos == 7
    assert featurize("q", install={"repos": ["a", "b"]}).workspace_repos == 2
    assert featurize("q", install={}).log_workspace_repos == 0.0


def test_approx_tokens_is_chars_over_four_rounded_up():
    assert featurize("x" * 9).approx_tokens == 3


def test_featurize_is_deterministic():
    q = "Why did build #12 fail on main?"
    assert featurize(q) == featurize(q)
