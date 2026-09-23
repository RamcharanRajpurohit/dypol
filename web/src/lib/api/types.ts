/**
 * Mirrors backend/app/models/schemas.py.
 * Keep in sync if backend schemas change.
 */

export type Status = "ok" | "hot" | "stuck" | "neutral";
export type PRState = "open" | "closed" | "merged";
export type AlertKind =
  | "stuck_pr"
  | "failing_check"
  | "dependabot"
  | "code_scanning"
  | "secret_scanning";
export type Severity = "low" | "medium" | "high" | "critical";

export interface Member {
  login: string;
  name: string | null;
  avatar_url: string;
  role: string | null;
  html_url: string;
}

export interface Repo {
  name: string;
  full_name: string;
  private: boolean;
  archived: boolean;
  default_branch: string;
  open_issues_count: number;
  open_prs: number;
  /** open_prs is a lower bound (org-wide PR sweep was capped). */
  open_prs_approx: boolean;
  pushed_at: string | null;
  status: Status;
  summary: string;
  spark: number[];
  html_url: string;
}

export interface PR {
  repo: string;
  number: number;
  title: string;
  state: PRState;
  author: string | null;
  created_at: string;
  updated_at: string;
  merged_at: string | null;
  additions: number | null;
  deletions: number | null;
  review_count: number;
  comments: number;
  draft: boolean;
  html_url: string;
}

export interface ActivityEvent {
  id: string;
  type: string;
  actor: string;
  actor_avatar: string;
  repo: string;
  summary: string;
  created_at: string;
}

export interface Contributor {
  login: string;
  name: string | null;
  avatar_url: string;
  commits: number;
  additions: number;
  deletions: number;
  prs_merged: number;
  reviews: number;
  score: number;
}

export interface LeaderboardEntry extends Contributor {
  rank: number;
  delta: number;
}

export interface Alert {
  kind: AlertKind;
  repo: string;
  ref: string;
  title: string;
  severity: Severity;
  url: string;
  created_at: string;
}

export interface DigestSummary {
  period_start: string;
  period_end: string;
  prs_opened: number;
  prs_merged: number;
  commits: number;
  reviews: number;
  top_contributors: Contributor[];
  top_repos: Repo[];
}

export interface AskSourceItem {
  t: string;
  d: string;
  url: string | null;
}

export interface AskSourceGroup {
  kind: string;
  items: AskSourceItem[];
}

export interface AskAnswer {
  q: string;
  answer: string;
  sources: AskSourceGroup[];
  followups: string[];
}

// ── Chat (agentic) ──────────────────────────────────────────────
export interface ChatToolCall {
  name: string;
  args: Record<string, unknown>;
  result_preview: string | null;
  duration_ms: number | null;
}

export interface ChatMessage {
  id: string;
  session_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  tool_calls: ChatToolCall[];
  /** Set only on the assistant's quota-exhausted notice message. */
  quota: QuotaInfo | null;
  created_at: string;
}

/** Daily chat-call quota. All values are computed server-side; read-only. */
export interface QuotaInfo {
  used: number;
  /** <= 0 means unlimited (quota disabled). */
  limit: number;
  /** Next UTC-midnight rollover (backend clock). */
  resets_at: string;
}

export interface ChatSession {
  id: string;
  user_id: number;
  org: string;
  title: string;
  pinned: boolean;
  archived: boolean;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_message_preview: string | null;
}

export interface ChatTurnResponse {
  session: ChatSession;
  user_message: ChatMessage;
  assistant_message: ChatMessage;
  /** Remaining daily calls after this turn (null when quota is disabled). */
  quota: QuotaInfo | null;
}

// ── Chat streaming (SSE) ─────────────────────────────────────────
// Payloads for the `POST /chat/sessions/{id}/messages/stream` SSE endpoint.
// Each SSE frame is `event: <type>` + `data: <json>`.

/** `event: token` — an incremental chunk of assistant text. */
export interface ChatStreamTokenEvent {
  delta: string;
}

/**
 * `event: tool` — a live tool / sub-agent trace row.
 *
 * `name` may be:
 *   - a plain tool name, e.g. `"github_get"`
 *   - a `"<label>→<tool>"` pair scoping a tool to a sub-agent, e.g. `"code_analyst→github_get"`
 *   - a `"delegate_<name>"` group header, e.g. `"delegate_code_analyst"`
 *
 * `phase` is `"start"` when the tool is invoked and `"end"` when it resolves.
 */
export interface ChatStreamToolEvent {
  name: string;
  args: Record<string, unknown>;
  result_preview: string | null;
  duration_ms: number | null;
  phase: "start" | "end";
}

/** `event: error` — a terminal error for the stream. */
export interface ChatStreamErrorEvent {
  message: string;
}

/** `event: done` carries the same {@link ChatTurnResponse} as the non-streaming endpoint. */
export type ChatStreamDoneEvent = ChatTurnResponse;

/** Callbacks invoked while consuming the SSE stream. */
export interface ChatStreamHandlers {
  onToken?: (delta: string) => void;
  onTool?: (event: ChatStreamToolEvent) => void;
  onDone?: (turn: ChatTurnResponse) => void;
  onError?: (message: string) => void;
}

export interface Kpi {
  label: string;
  value: number;
  unit: string | null;
  delta: number | null;
  delta_pct: number | null;
  spark: number[];
  direction: "up" | "down" | "flat";
  sentiment: "good" | "bad" | "neutral";
}

export interface DashboardSummary {
  org: string;
  org_type: string | null;
  mode: WorkspaceMode;
  period_label: string;
  headline: string;
  kpis: Kpi[];
  repos_total: number;
  repos: Repo[];
  top_contributors: Contributor[];
  top_alerts: Alert[];
  alerts_total: number;
  recent_activity: ActivityEvent[];
}

export type WorkspaceMode = "install" | "public";

export interface Installation {
  install_id: number | null;
  account_login: string;
  account_type: string | null;
  repository_selection: string | null;
  mode: WorkspaceMode;
  avatar_url: string | null;
}

export interface MeResponse {
  user: {
    login: string;
    name: string | null;
    email: string | null;
    avatar_url: string | null;
  };
  installations: Installation[];
  /** Set when the first-sign-in default-workspace auto-add failed, so the
   *  connection screen can explain why instead of showing a mystery empty
   *  state. Never set by the backend — the client attaches it. */
  defaultWorkspaceError?: string;
}

export interface ConnectedAccount {
  type: "User" | "Organization";
  login: string;
  id: number | null;
  avatar_url: string | null;
  installed: true;
  install_id: number | null;
  mode: WorkspaceMode;
  repository_selection: string | null;
  repositories_count: number;
}

export interface ConnectionsResponse {
  connected: ConnectedAccount[];
  install_url: string;
}

/** One hit from the public-account type-ahead (`GET /workspaces/search`). */
export interface AccountSearchResult {
  login: string;
  name: string | null;
  avatar_url: string | null;
  type: "User" | "Organization";
  description: string;
  public_repos: number;
  followers: number;
  html_url: string | null;
  /** True when this user already has a workspace for the account. */
  already_added: boolean;
}

export interface AccountSearchResponse {
  query: string;
  results: AccountSearchResult[];
  /** GitHub's shared search budget is spent — results are empty, not wrong. */
  rate_limited: boolean;
}
