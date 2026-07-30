from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Status = Literal["ok", "hot", "stuck", "neutral"]
PRState = Literal["open", "closed", "merged"]
AlertKind = Literal["stuck_pr", "failing_check", "dependabot", "code_scanning", "secret_scanning"]
Severity = Literal["low", "medium", "high", "critical"]


class Member(BaseModel):
    login: str
    name: str | None = None
    avatar_url: str
    role: str | None = None
    html_url: str


class Repo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name: str
    full_name: str
    private: bool
    archived: bool
    default_branch: str
    open_issues_count: int = 0
    open_prs: int = 0
    # True when ``open_prs`` is a LOWER BOUND: list views count open PRs with a
    # capped org-wide search sweep, so a very busy account can have more than
    # were seen. The UI renders these as "78+" rather than claiming exactness.
    open_prs_approx: bool = False
    pushed_at: datetime | None = None
    status: Status = "neutral"
    summary: str = ""
    spark: list[int] = Field(default_factory=list)
    html_url: str


class PR(BaseModel):
    repo: str
    number: int
    title: str
    state: PRState
    author: str | None = None
    created_at: datetime
    updated_at: datetime
    merged_at: datetime | None = None
    additions: int | None = None
    deletions: int | None = None
    review_count: int = 0
    comments: int = 0
    draft: bool = False
    html_url: str


class Commit(BaseModel):
    sha: str
    repo: str
    author_login: str | None = None
    author_name: str | None = None
    message: str
    additions: int | None = None
    deletions: int | None = None
    committed_at: datetime
    html_url: str


class ActivityEvent(BaseModel):
    id: str
    type: str
    actor: str
    actor_avatar: str
    repo: str
    summary: str
    created_at: datetime


class Contributor(BaseModel):
    login: str
    name: str | None = None
    avatar_url: str
    commits: int = 0
    additions: int = 0
    deletions: int = 0
    prs_merged: int = 0
    reviews: int = 0
    score: float = 0.0


class LeaderboardEntry(Contributor):
    rank: int
    delta: float = 0.0


class Alert(BaseModel):
    kind: AlertKind
    repo: str
    ref: str
    title: str
    severity: Severity = "medium"
    url: str
    created_at: datetime


class DigestSummary(BaseModel):
    period_start: datetime
    period_end: datetime
    prs_opened: int
    prs_merged: int
    commits: int
    reviews: int
    top_contributors: list[Contributor]
    top_repos: list[Repo]


class AskRequest(BaseModel):
    q: str
    repo: str | None = None
    limit: int = 20


class AskSourceItem(BaseModel):
    t: str
    d: str
    url: str | None = None


class AskSourceGroup(BaseModel):
    kind: str
    items: list[AskSourceItem]


class AskAnswer(BaseModel):
    q: str
    answer: str
    sources: list[AskSourceGroup]
    followups: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    ok: bool
    org: str
    db: bool
    github: bool


# ──────────────────────────────────────────────────────────────────
# Chat — agentic, multi-turn, tool-using
# ──────────────────────────────────────────────────────────────────
class ChatToolCall(BaseModel):
    """One tool invocation made by the model during a turn."""
    name: str
    args: dict
    result_preview: str | None = None       # short preview for UI trace
    duration_ms: int | None = None


class ChatMessage(BaseModel):
    id: str
    session_id: str
    role: Literal["user", "assistant", "system"]
    content: str
    tool_calls: list[ChatToolCall] = Field(default_factory=list)
    created_at: datetime


class ChatSession(BaseModel):
    id: str
    user_id: int
    org: str
    title: str
    pinned: bool = False
    archived: bool = False
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    last_message_preview: str | None = None


class ChatSessionList(BaseModel):
    sessions: list[ChatSession]


class ChatSendRequest(BaseModel):
    content: str


class ChatTurnResponse(BaseModel):
    """Response shape after the model finishes a turn (possibly multi-step
    via tool calls)."""
    session: ChatSession
    user_message: ChatMessage
    assistant_message: ChatMessage


class Kpi(BaseModel):
    label: str
    value: float
    unit: str | None = None
    delta: float | None = None       # absolute delta vs previous period
    delta_pct: float | None = None   # pct change vs previous period
    spark: list[float] = Field(default_factory=list)  # 12-week trend
    direction: Literal["up", "down", "flat"] = "flat"
    sentiment: Literal["good", "bad", "neutral"] = "neutral"


class DashboardSummary(BaseModel):
    org: str
    org_type: str | None = None
    mode: Literal["install", "public"] = "install"
    period_label: str                          # "Week of May 4"
    headline: str                              # one-line narrative
    kpis: list[Kpi]
    repos_total: int
    repos: list[Repo]                          # top by activity
    top_contributors: list[Contributor]
    top_alerts: list[Alert]                    # max 3, curated
    alerts_total: int
    recent_activity: list[ActivityEvent]
