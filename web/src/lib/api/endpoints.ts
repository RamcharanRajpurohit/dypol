/**
 * High-level API helpers — one function per endpoint.
 *
 * All functions are thin: take params, call `api(...)`, return typed data.
 * Components should use these instead of touching `fetch` directly.
 */
import { api, apiUrl, sseStream } from "./client";
import type {
  AccountSearchResponse,
  Alert,
  ActivityEvent,
  AskAnswer,
  ChatMessage,
  ChatSession,
  ChatStreamHandlers,
  ChatStreamErrorEvent,
  ChatStreamToolEvent,
  ChatStreamTokenEvent,
  ChatTurnResponse,
  ConnectionsResponse,
  DashboardSummary,
  DigestSummary,
  LeaderboardEntry,
  Member,
  MeResponse,
  PR,
  Repo,
} from "./types";

// ── Auth ────────────────────────────────────────────────────────────
export const loginUrl = () => apiUrl("/auth/login");
export const installUrl = () => apiUrl("/auth/install");
export const logout = () => api<unknown>("/auth/logout", { method: "POST" });
export const me = () => api<MeResponse>("/auth/me");
export const listConnections = () => api<ConnectionsResponse>("/auth/orgs");

// Public-org workspaces (no GitHub App install required)
export const searchAccounts = (q: string, limit = 6) =>
  api<AccountSearchResponse>("/workspaces/search", { query: { q, limit } });

export const addPublicWorkspace = (login: string) =>
  api<unknown>("/workspaces/public", { method: "POST", body: { login } });

export const removePublicWorkspace = (login: string) =>
  api<unknown>(`/workspaces/public/${login}`, { method: "DELETE" });

// ── Views ───────────────────────────────────────────────────────────
export const getDashboard = (org?: string) =>
  api<DashboardSummary>("/dashboard/", { query: { org } });

export const getRepos = (org?: string, includeArchived = false) =>
  api<Repo[]>("/repos/", { query: { org, include_archived: includeArchived } });

export const getRepo = (name: string, org?: string) =>
  api<Repo>(`/repos/${name}`, { query: { org } });

export const getRepoPrs = (
  name: string,
  state: "open" | "closed" | "all" = "all",
  limit = 50,
  org?: string,
) => api<PR[]>(`/repos/${name}/prs`, { query: { state, limit, org } });

export const getLeaderboard = (days = 30, limit = 25, org?: string) =>
  api<LeaderboardEntry[]>("/leaderboard/", { query: { days, limit, org } });

export const getActivity = (limit = 50, org?: string) =>
  api<ActivityEvent[]>("/activity/", { query: { limit, org } });

export const getAlerts = (limit = 100, org?: string) =>
  api<Alert[]>("/alerts/", { query: { limit, org } });

export const getDigest = (days = 7, org?: string) =>
  api<DigestSummary>("/digest/", { query: { days, org } });

export const ask = (q: string, repo?: string, limit = 20, org?: string) =>
  api<AskAnswer>("/ask/", {
    method: "POST",
    body: { q, repo, limit },
    query: { org },
  });

export const getOrgInfo = (org?: string) =>
  api<{ org: string; account_type: string; user_login: string }>(
    "/settings/org",
    { query: { org } },
  );

export const getMembers = (org?: string) =>
  api<Member[]>("/settings/members", { query: { org } });

// ── Chat ────────────────────────────────────────────────────────
export const chatStatus = () =>
  api<{ agent_enabled: boolean }>("/chat/status");

// `org` is passed explicitly rather than relying on the module-level default:
// the sidebar loads sessions from a child effect that can run before the org
// provider's effect has (re)published the default, and a request with no org
// 400s with `org_required` whenever the user has more than one workspace.
export const listChatSessions = (includeArchived = false, org?: string) =>
  api<ChatSession[]>("/chat/sessions", {
    query: { include_archived: includeArchived, org },
  });

export const createChatSession = () =>
  api<ChatSession>("/chat/sessions", { method: "POST" });

export const getChatSession = (id: string) =>
  api<ChatSession>(`/chat/sessions/${id}`);

export const patchChatSession = (
  id: string,
  fields: Partial<Pick<ChatSession, "title" | "pinned" | "archived">>,
) =>
  api<ChatSession>(`/chat/sessions/${id}`, { method: "PATCH", body: fields });

export const deleteChatSession = (id: string) =>
  api<unknown>(`/chat/sessions/${id}`, { method: "DELETE" });

export const listChatMessages = (sessionId: string) =>
  api<ChatMessage[]>(`/chat/sessions/${sessionId}/messages`);

export const sendChatMessage = (sessionId: string, content: string) =>
  api<ChatTurnResponse>(`/chat/sessions/${sessionId}/messages`, {
    method: "POST",
    body: { content },
  });

/**
 * Send a chat message over the streaming (SSE) endpoint, dispatching frames to
 * `handlers` as they arrive. Resolves once the `done` frame is received and the
 * stream closes; the resolved value is the final {@link ChatTurnResponse}, or
 * `null` if the stream ended without a `done` frame.
 *
 * Throws `ApiError` if the endpoint responds non-2xx before streaming (e.g. a
 * 404 when the stream endpoint isn't deployed) — callers can catch this and
 * fall back to {@link sendChatMessage}. The org is scoped automatically, exactly
 * like every other call (the active org is auto-attached as `?org=…`).
 *
 * @param signal optional AbortSignal to cancel the in-flight stream.
 */
export async function sendChatMessageStream(
  sessionId: string,
  content: string,
  handlers: ChatStreamHandlers,
  signal?: AbortSignal,
): Promise<ChatTurnResponse | null> {
  let result: ChatTurnResponse | null = null;
  for await (const frame of sseStream(
    `/chat/sessions/${sessionId}/messages/stream`,
    { body: { content }, signal },
  )) {
    switch (frame.event) {
      case "token": {
        const payload = parseStreamJson<ChatStreamTokenEvent>(frame.data);
        if (payload && typeof payload.delta === "string") {
          handlers.onToken?.(payload.delta);
        }
        break;
      }
      case "tool": {
        const payload = parseStreamJson<ChatStreamToolEvent>(frame.data);
        if (payload && typeof payload.name === "string") {
          handlers.onTool?.(payload);
        }
        break;
      }
      case "done": {
        const payload = parseStreamJson<ChatTurnResponse>(frame.data);
        if (payload) {
          result = payload;
          handlers.onDone?.(payload);
        }
        break;
      }
      case "error": {
        const payload = parseStreamJson<ChatStreamErrorEvent>(frame.data);
        handlers.onError?.(payload?.message ?? "Streaming error");
        break;
      }
      default:
        // Ignore unknown / keep-alive frames.
        break;
    }
  }
  return result;
}

function parseStreamJson<T>(data: string): T | null {
  try {
    return JSON.parse(data) as T;
  } catch {
    return null;
  }
}
