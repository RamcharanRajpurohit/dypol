"""Difficulty features — the context vector a policy decides from (§6).

Everything here is computed from the question text, the prior conversation
and the workspace dict, with **no LLM call and no I/O** — featurisation runs on
every turn before anything is spent, so it must cost microseconds, not cents.

The features are intentionally coarse. They don't need to *answer* "how hard
is this question"; they need to separate the cases the current constants
treat identically — "how many PRs merged last week" vs "why did the auth
refactor break billing" — well enough for a linear model to learn from.
"""
from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from typing import Any

# ── lexical signals ──────────────────────────────────────────────────
_CODE_FENCE = re.compile(r"```|`[^`\n]+`")
_FILE_PATH = re.compile(
    r"\b[\w.-]+/[\w./-]+\.\w{1,5}\b"
    r"|\b\w+\.(?:py|ts|tsx|js|go|rs|java|rb|md|yml|yaml|json|toml)\b"
)
_IDENTIFIER = re.compile(r"\b[a-z]+(?:_[a-z0-9]+)+\b|\b[a-z]+(?:[A-Z][a-z0-9]+)+\b")
_PR_REF = re.compile(r"(?:#\d+\b|\bPR\s*\d+\b|\bpull request\s*\d+\b)", re.IGNORECASE)
_REPO_REF = re.compile(r"\b[\w-]+/[\w.-]+\b")
_URL = re.compile(r"https?://\S+")
_WORD = re.compile(r"[A-Za-z0-9_']+")

# Question-type cue words. A turn can match several; the type is the strongest.
_CUES: dict[str, tuple[str, ...]] = {
    "metric": (
        "how many", "count", "number of", "total", "average", "median", "rate",
        "trend", "last week", "this week", "last month", "per day", "velocity",
        "leaderboard", "top ", "most active", "merged", "opened", "closed",
    ),
    "code": (
        "why does", "why did", "how does", "how is", "implement", "function",
        "class ", "bug", "refactor", "stack trace", "exception", "error",
        "code", "file", "module", "architecture", "explain", "where is",
    ),
    "web": (
        "latest", "news", "release notes", "changelog", "cve", "vulnerability",
        "best practice", "compare", "vs ", "versus", "documentation", "docs",
    ),
    "smalltalk": ("hi", "hello", "hey", "thanks", "thank you", "good morning"),
}
QUESTION_TYPES: tuple[str, ...] = ("metric", "code", "web", "smalltalk", "other")

_STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "by", "did", "do", "does",
        "for", "from", "how", "i", "in", "is", "it", "of", "on", "or", "our",
        "the", "this", "to", "was", "we", "what", "when", "where", "which",
        "who", "why", "with", "you", "your",
    }
)


@dataclass(frozen=True, slots=True)
class TurnFeatures:
    """Numeric feature snapshot for one turn. All fields are floats so the
    vector can be fed to a linear model without further encoding."""

    query_chars: float = 0.0
    query_words: float = 0.0
    approx_tokens: float = 0.0
    has_code: float = 0.0
    file_paths: float = 0.0
    identifiers: float = 0.0
    pr_refs: float = 0.0
    repo_refs: float = 0.0
    urls: float = 0.0
    question_marks: float = 0.0
    type_metric: float = 0.0
    type_code: float = 0.0
    type_web: float = 0.0
    type_smalltalk: float = 0.0
    type_other: float = 0.0
    history_turns: float = 0.0
    history_chars: float = 0.0
    topical_continuity: float = 0.0
    workspace_repos: float = 0.0
    log_workspace_repos: float = 0.0

    @property
    def question_type(self) -> str:
        scores = {
            "metric": self.type_metric,
            "code": self.type_code,
            "web": self.type_web,
            "smalltalk": self.type_smalltalk,
            "other": self.type_other,
        }
        return max(scores, key=lambda k: scores[k])

    def as_dict(self) -> dict[str, float]:
        return asdict(self)

    def as_vector(self) -> list[float]:
        return [float(v) for v in asdict(self).values()]


FEATURE_NAMES: list[str] = list(TurnFeatures.__dataclass_fields__)


def _content_words(text: str) -> set[str]:
    return {w for w in (m.group(0).lower() for m in _WORD.finditer(text)) if w not in _STOPWORDS}


def _cue_hits(text: str) -> dict[str, int]:
    lowered = f" {text.lower()} "
    hits: dict[str, int] = {}
    for qtype, cues in _CUES.items():
        n = 0
        for cue in cues:
            if qtype == "smalltalk":
                # Whole-word match only — "hi" must not fire on "this".
                if re.search(rf"\b{re.escape(cue)}\b", lowered):
                    n += 1
            elif cue in lowered:
                n += 1
        hits[qtype] = n
    return hits


def _classify(text: str, words: int) -> dict[str, float]:
    """One-hot question type. Smalltalk only wins for short messages; a long
    question that happens to start with "hi" is still a real question."""
    hits = _cue_hits(text)
    if hits["smalltalk"] and words <= 6 and not (hits["metric"] or hits["code"] or hits["web"]):
        best = "smalltalk"
    else:
        ranked = sorted(
            ((hits[t], t) for t in ("code", "metric", "web")),
            key=lambda pair: pair[0],
            reverse=True,
        )
        best = ranked[0][1] if ranked[0][0] > 0 else "other"
    return {f"type_{t}": 1.0 if t == best else 0.0 for t in QUESTION_TYPES}


def _message_text(msg: Any) -> tuple[str, str]:
    """``(role, text)`` from a Mongo dict, a pydantic ChatMessage, or a
    LangChain message — the three shapes history arrives in."""
    if isinstance(msg, dict):
        return str(msg.get("role", "")), str(msg.get("content") or "")
    role = getattr(msg, "role", None) or getattr(msg, "type", "") or ""
    content = getattr(msg, "content", "") or ""
    if isinstance(content, list):  # multi-part LangChain content
        content = " ".join(
            part.get("text", "") if isinstance(part, dict) else str(part) for part in content
        )
    return str(role), str(content)


def _continuity(question: str, prior: list[Any]) -> float:
    """Jaccard overlap between this question and the previous user message.
    High → a follow-up that benefits from history; ~0 → a fresh topic."""
    last_user = ""
    for msg in reversed(prior):
        role, text = _message_text(msg)
        if role in ("user", "human"):
            last_user = text
            break
    if not last_user:
        return 0.0
    a, b = _content_words(question), _content_words(last_user)
    if not a or not b:
        return 0.0
    return round(len(a & b) / len(a | b), 4)


def featurize(
    question: str,
    prior: list[Any] | None = None,
    install: dict[str, Any] | None = None,
) -> TurnFeatures:
    """Compute :class:`TurnFeatures` for one turn. Never raises."""
    question = question or ""
    prior = prior or []
    install = install or {}

    words = len(_WORD.findall(question))
    history_chars = sum(len(_message_text(m)[1]) for m in prior)
    user_turns = sum(1 for m in prior if _message_text(m)[0] in ("user", "human"))
    repos = install.get("repo_count")
    if repos is None:
        repos = len(install.get("repos") or [])

    return TurnFeatures(
        query_chars=float(len(question)),
        query_words=float(words),
        # ~4 chars/token is the usual English heuristic; exact counts would
        # need the provider tokenizer, which is exactly the cost we avoid.
        approx_tokens=float(math.ceil(len(question) / 4)),
        has_code=1.0 if _CODE_FENCE.search(question) else 0.0,
        file_paths=float(len(_FILE_PATH.findall(question))),
        identifiers=float(len(_IDENTIFIER.findall(question))),
        pr_refs=float(len(_PR_REF.findall(question))),
        repo_refs=float(len(_REPO_REF.findall(_URL.sub("", question)))),
        urls=float(len(_URL.findall(question))),
        question_marks=float(question.count("?")),
        history_turns=float(user_turns),
        history_chars=float(history_chars),
        topical_continuity=_continuity(question, prior),
        workspace_repos=float(repos),
        log_workspace_repos=round(math.log1p(float(repos)), 4),
        **_classify(question, words),
    )
