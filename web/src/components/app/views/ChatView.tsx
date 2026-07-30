"use client";

/**
 * Agentic chat view — controlled by parent.
 *
 * The session list lives in AppShell (so the AppShell sidebar can render
 * it). ChatView only manages the *current* conversation: messages,
 * composer, sending state, optimistic updates.
 *
 * Sending prefers the streaming SSE endpoint: the assistant bubble fills in
 * live and tool / sub-agent steps appear as they run. If streaming throws,
 * aborts, or the endpoint isn't deployed (404), we transparently fall back to
 * the non-streaming `sendChatMessage` call so nothing breaks.
 *
 * Parent passes:
 *   - sessionId            — null until a session is created
 *   - onSessionUpdated     — fires after a turn (new title / preview)
 *   - onSessionCreated     — fires when ChatView creates a session on the
 *                            user's first message
 */
import {
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ApiError,
  createChatSession,
  listChatMessages,
  sendChatMessage,
  sendChatMessageStream,
} from "@/lib/api";
import type {
  ChatMessage,
  ChatSession,
  ChatStreamToolEvent,
  ChatToolCall,
} from "@/lib/api";
import { useOrg } from "@/lib/api/OrgContext";
import { ArrowSendIcon } from "../icons";

const SUGGESTIONS: ReadonlyArray<string> = [
  "What changed in the last 7 days?",
  "Which PRs are stuck waiting for review?",
  "Who has been most active recently?",
  "What's failing CI right now?",
];

export interface ChatViewHandle {
  ask: (question: string) => void;
  reset: () => void;
}

interface Props {
  visible: boolean;
  sessionId: string | null;
  onSessionCreated: (s: ChatSession) => void;
  onSessionUpdated: (s: ChatSession) => void;
  ref?: React.Ref<ChatViewHandle>;
  onActiveQuestionChange?: (q: string | null) => void;
}

/**
 * A live tool/sub-agent row, accumulated from streamed `tool` events. We track
 * `pending` so phase=start rows without a matching phase=end show a spinner.
 */
interface LiveTool extends ChatToolCall {
  pending: boolean;
}

export function ChatView({
  visible,
  sessionId,
  onSessionCreated,
  onSessionUpdated,
  ref,
  onActiveQuestionChange,
}: Props) {
  const { activeOrg } = useOrg();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [composer, setComposer] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Live-stream state for the in-flight assistant turn.
  const [streamText, setStreamText] = useState("");
  const [liveTools, setLiveTools] = useState<LiveTool[]>([]);
  const [streaming, setStreaming] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // ── Load messages when active session changes ──
  useEffect(() => {
    if (!sessionId) {
      setMessages([]);
      return;
    }
    let cancelled = false;
    listChatMessages(sessionId)
      .then((m) => {
        if (!cancelled) setMessages(m);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  // Notify parent of active question (for sidebar highlight legacy)
  useEffect(() => {
    const last = [...messages].reverse().find((m) => m.role === "user");
    onActiveQuestionChange?.(last?.content ?? null);
  }, [messages, onActiveQuestionChange]);

  // Scroll to bottom on new message or while streaming.
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, sending, streamText, liveTools]);

  const ensureSession = useCallback(async (): Promise<string> => {
    if (sessionId) return sessionId;
    const s = await createChatSession();
    onSessionCreated(s);
    return s.id;
  }, [sessionId, onSessionCreated]);

  // Apply a streamed `tool` event into the live-tools list. A phase=end row
  // resolves the most recent matching pending row (same name); otherwise it
  // appends a fresh row.
  const applyToolEvent = useCallback((ev: ChatStreamToolEvent) => {
    setLiveTools((prev) => {
      if (ev.phase === "end") {
        const idx = findLastPendingIndex(prev, ev.name);
        if (idx !== -1) {
          const next = prev.slice();
          next[idx] = {
            name: ev.name,
            args: ev.args,
            result_preview: ev.result_preview,
            duration_ms: ev.duration_ms,
            pending: false,
          };
          return next;
        }
      }
      return [
        ...prev,
        {
          name: ev.name,
          args: ev.args,
          result_preview: ev.result_preview,
          duration_ms: ev.duration_ms,
          pending: ev.phase === "start",
        },
      ];
    });
  }, []);

  const sendNow = useCallback(
    async (text: string) => {
      const v = text.trim();
      if (!v || sending) return;
      setError(null);
      setSending(true);
      setStreamText("");
      setLiveTools([]);
      setStreaming(false);
      const tempId = `temp-${Date.now()}`;
      const optimistic: ChatMessage = {
        id: tempId,
        session_id: "",
        role: "user",
        content: v,
        tool_calls: [],
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, optimistic]);

      const commitTurn = (
        userMessage: ChatMessage,
        assistantMessage: ChatMessage,
        session: ChatSession,
      ) => {
        setMessages((prev) => [
          ...prev.filter((m) => m.id !== tempId),
          userMessage,
          assistantMessage,
        ]);
        onSessionUpdated(session);
      };

      try {
        const sid = await ensureSession();
        // Holder object (not a plain `let`) so the callback mutation is visible
        // to control flow after the await without being narrowed to `null`.
        const streamErr = { message: null as string | null };
        try {
          setStreaming(true);
          const resp = await sendChatMessageStream(sid, v, {
            onToken: (delta) => setStreamText((t) => t + delta),
            onTool: (ev) => applyToolEvent(ev),
            onError: (msg) => {
              streamErr.message = msg;
            },
          });
          if (resp) {
            commitTurn(resp.user_message, resp.assistant_message, resp.session);
            return;
          }
          // Stream closed without a terminal `done` frame → treat as a miss
          // and fall through to the non-streaming path below.
          if (streamErr.message) throw new Error(streamErr.message);
        } catch (caught) {
          // A 404 means the stream endpoint isn't deployed — fall back. Any
          // other stream failure also falls back to the proven path so the
          // user still gets an answer.
          if (
            caught instanceof ApiError &&
            caught.status !== 404 &&
            caught.status >= 400 &&
            caught.status < 500 &&
            caught.status !== 408
          ) {
            // A genuine client error (e.g. 401/403/422) won't succeed on the
            // non-streaming endpoint either — surface it.
            throw caught;
          }
          // else: fall through to fallback.
        } finally {
          setStreaming(false);
        }

        // ── Fallback: non-streaming endpoint ──
        const resp = await sendChatMessage(sid, v);
        commitTurn(resp.user_message, resp.assistant_message, resp.session);
      } catch (err) {
        setMessages((prev) => prev.filter((m) => m.id !== tempId));
        if (err instanceof ApiError) setError(`${err.status}: ${err.message}`);
        else setError(err instanceof Error ? err.message : String(err));
      } finally {
        setSending(false);
        setStreaming(false);
        setStreamText("");
        setLiveTools([]);
      }
    },
    [sending, ensureSession, onSessionUpdated, applyToolEvent],
  );

  useImperativeHandle(
    ref,
    () => ({
      ask: (q: string) => void sendNow(q),
      reset: () => {
        setMessages([]);
        setComposer("");
        setStreamText("");
        setLiveTools([]);
        setStreaming(false);
        inputRef.current?.focus();
      },
    }),
    [sendNow],
  );

  if (!visible) return null;

  const submit = () => {
    const v = composer.trim();
    if (!v) return;
    setComposer("");
    void sendNow(v);
  };

  // While streaming, show a live assistant bubble (tools + partial text). The
  // thinking indicator only shows before the first token / tool arrives.
  const hasLiveContent = streamText.length > 0 || liveTools.length > 0;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        minHeight: 0,
      }}
    >
      <div ref={scrollRef} className="scroll" style={{ flex: 1, overflowY: "auto" }}>
        <div
          style={{
            maxWidth: 760,
            margin: "0 auto",
            padding: "32px 32px 16px",
          }}
        >
          {error && <p style={{ color: "var(--hot)", fontSize: 13 }}>{error}</p>}
          {messages.length === 0 && !sending && (
            <Welcome onPick={(q) => void sendNow(q)} />
          )}
          {messages.map((m) => (
            <MessageBubble key={m.id} message={m} />
          ))}
          {sending && hasLiveContent && (
            <StreamingBubble text={streamText} tools={liveTools} />
          )}
          {sending && !hasLiveContent && <ThinkingIndicator />}
        </div>
      </div>

      <div
        className="hairline"
        style={{
          borderTop: "1px solid var(--hairline)",
          padding: 16,
          background: "var(--bg)",
        }}
      >
        <form
          className="composer"
          style={{ maxWidth: 760, margin: "0 auto" }}
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <textarea
            ref={inputRef}
            value={composer}
            onChange={(e) => setComposer(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            placeholder="Ask anything about your engineering org…"
            rows={1}
            disabled={sending}
          />
          <div className="composer-actions">
            <span className="chip">@ scope: {activeOrg ?? "—"}</span>
            <div className="flex items-center gap-2">
              {streaming && (
                <span className="caption" style={{ color: "var(--ink3)" }}>
                  <span
                    className="pulse-mini"
                    style={{ background: "var(--accent)", display: "inline-block" }}
                  />{" "}
                  live
                </span>
              )}
              <span className="label-tight hidden sm:inline">⏎ to send</span>
              <button
                type="submit"
                className="btn-primary-sm"
                disabled={sending || !composer.trim()}
              >
                Send
                <ArrowSendIcon />
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}

/** Find the most-recent still-pending row matching `name`, or -1. */
function findLastPendingIndex(rows: LiveTool[], name: string): number {
  for (let i = rows.length - 1; i >= 0; i--) {
    const r = rows[i];
    if (r && r.pending && r.name === name) return i;
  }
  return -1;
}

// ──────────────────────────────────────────────────────────────────
// Welcome state — shown when conversation is empty
// ──────────────────────────────────────────────────────────────────
function Welcome({ onPick }: { onPick: (q: string) => void }) {
  return (
    <div style={{ paddingTop: 32 }}>
      <div className="caption mb-2">DyPol AI</div>
      <h1 className="display" style={{ fontSize: 28, lineHeight: 1.15 }}>
        What would you like to know?
      </h1>
      <p className="text-ink2 mt-2" style={{ fontSize: 14 }}>
        Ask about your repos, contributors, PRs, or anything else. The agent
        will pull the relevant data for you.
      </p>
      <div className="mt-6 flex flex-wrap gap-2">
        {SUGGESTIONS.map((s) => (
          <button key={s} type="button" className="chip" onClick={() => onPick(s)}>
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────
// Live streaming assistant bubble (text + tool trace, building in place)
// ──────────────────────────────────────────────────────────────────
function StreamingBubble({ text, tools }: { text: string; tools: LiveTool[] }) {
  return (
    <div style={{ marginBottom: 24 }}>
      <div className="caption" style={{ marginBottom: 6, color: "var(--ink3)" }}>
        DyPol
      </div>
      {tools.length > 0 && <ToolTrace calls={tools} live defaultOpen />}
      {text ? (
        <div style={{ marginTop: tools.length > 0 ? 10 : 0 }}>
          <MarkdownContent content={text} />
          <span className="stream-caret" aria-hidden>
            ▍
          </span>
        </div>
      ) : (
        <div style={{ marginTop: 8 }}>
          <ThinkingIndicator />
        </div>
      )}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────
// Message bubble
// ──────────────────────────────────────────────────────────────────
function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  const isQuota =
    !isUser && /rate limit|RESOURCE_EXHAUSTED|quota/i.test(message.content);
  // The user's own turns sit on the right in a bubble; the assistant's answer
  // stays full-width on the left, where long markdown, tables and tool traces
  // have room to breathe.
  if (isUser) {
    return (
      <div
        style={{
          marginBottom: 24,
          display: "flex",
          flexDirection: "column",
          alignItems: "flex-end",
        }}
      >
        <div className="caption" style={{ marginBottom: 6, color: "var(--ink3)" }}>
          You
        </div>
        <div
          style={{
            maxWidth: "76%",
            padding: "10px 14px",
            borderRadius: "12px 12px 3px 12px",
            background: "var(--accent2)",
            border: "1px solid var(--hairline)",
            fontSize: 14.5,
            lineHeight: 1.6,
            color: "var(--ink)",
            whiteSpace: "pre-wrap",
            overflowWrap: "anywhere",
            textAlign: "left",
          }}
        >
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div style={{ marginBottom: 24 }}>
      <div className="caption" style={{ marginBottom: 6, color: "var(--ink3)" }}>
        DyPol
      </div>
      {message.tool_calls.length > 0 && (
        <ToolTrace calls={message.tool_calls.map(toLiveTool)} />
      )}
      {isQuota ? (
        <div
          className="card"
          style={{
            padding: "12px 16px",
            background: "var(--warm-tint)",
            border: "1px solid var(--hairline)",
            display: "flex",
            alignItems: "center",
            gap: 10,
            marginTop: message.tool_calls.length > 0 ? 10 : 0,
          }}
        >
          <span className="dot stuck" />
          <span style={{ fontSize: 13.5, color: "var(--ink2)" }}>
            {message.content}
          </span>
        </div>
      ) : (
        <div style={{ marginTop: message.tool_calls.length > 0 ? 10 : 0 }}>
          <MarkdownContent content={message.content} />
        </div>
      )}
    </div>
  );
}

const toLiveTool = (c: ChatToolCall): LiveTool => ({ ...c, pending: false });

// ──────────────────────────────────────────────────────────────────
// Markdown — assistant content. Raw HTML is NOT enabled (react-markdown
// escapes it by default), so this is safe to render untrusted model output.
// ──────────────────────────────────────────────────────────────────
function MarkdownContent({ content }: { content: string }) {
  return (
    <div className="md" style={{ fontSize: 14.5, lineHeight: 1.6, color: "var(--ink)" }}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noreferrer noopener"
              style={{ color: "var(--accent)", textDecoration: "underline" }}
            >
              {children}
            </a>
          ),
          code: ({ className, children }) => {
            const isBlock = (className ?? "").startsWith("language-");
            if (isBlock) {
              return <code className={`mono ${className ?? ""}`}>{children}</code>;
            }
            return (
              <code
                className="mono"
                style={{
                  fontSize: "0.88em",
                  background: "var(--surface)",
                  border: "1px solid var(--hairline)",
                  borderRadius: 4,
                  padding: "1px 4px",
                }}
              >
                {children}
              </code>
            );
          },
          pre: ({ children }) => (
            <pre
              className="hairline"
              style={{
                background: "var(--surface)",
                border: "1px solid var(--hairline)",
                borderRadius: 6,
                padding: "10px 12px",
                overflowX: "auto",
                fontSize: 12.5,
                margin: "8px 0",
              }}
            >
              {children}
            </pre>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────
// Tool trace — renders sub-agent hierarchy.
//   • "delegate_<name>"  → a group header for a delegated sub-agent
//   • "label→tool"        → a tool indented under its sub-agent's group
//   • "tool"              → a plain top-level tool row
// Rows still pending (phase=start, no end) show a spinner.
// ──────────────────────────────────────────────────────────────────

interface TraceGroup {
  /** Sub-agent label (from a delegate_* header or a "label→tool" prefix), or null for top-level. */
  label: string | null;
  /** The delegate_* header row itself, if present. */
  header: LiveTool | null;
  /** Tools that belong under this group. */
  tools: LiveTool[];
}

/** Split a tool name into its optional sub-agent label and tool name. */
function parseToolName(name: string): { label: string | null; tool: string } {
  const arrow = name.indexOf("→");
  if (arrow !== -1) {
    return { label: name.slice(0, arrow).trim(), tool: name.slice(arrow + 1).trim() };
  }
  return { label: null, tool: name };
}

const isDelegateRow = (name: string) => name.startsWith("delegate_");
const delegateLabel = (name: string) => name.slice("delegate_".length);

/** Group a flat list of tool rows into sub-agent hierarchy, preserving order. */
function buildGroups(calls: LiveTool[]): TraceGroup[] {
  const groups: TraceGroup[] = [];
  const byLabel = new Map<string, TraceGroup>();

  const ensureGroup = (label: string | null): TraceGroup => {
    if (label === null) {
      // Top-level rows share one (unkeyed) running group only when adjacent;
      // to keep it simple we use a single shared bucket keyed by "".
      const existing = byLabel.get("");
      if (existing) return existing;
      const g: TraceGroup = { label: null, header: null, tools: [] };
      byLabel.set("", g);
      groups.push(g);
      return g;
    }
    const existing = byLabel.get(label);
    if (existing) return existing;
    const g: TraceGroup = { label, header: null, tools: [] };
    byLabel.set(label, g);
    groups.push(g);
    return g;
  };

  for (const c of calls) {
    if (isDelegateRow(c.name)) {
      const g = ensureGroup(delegateLabel(c.name));
      g.header = c;
      continue;
    }
    const { label } = parseToolName(c.name);
    ensureGroup(label).tools.push(c);
  }
  return groups;
}

function ToolTrace({
  calls,
  live = false,
  defaultOpen = false,
}: {
  calls: LiveTool[];
  live?: boolean;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const totalMs = calls.reduce((a, c) => a + (c.duration_ms ?? 0), 0);
  const anyPending = calls.some((c) => c.pending);
  const groups = useMemo(() => buildGroups(calls), [calls]);

  return (
    <div style={{ marginTop: 10 }}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="mono"
        style={{
          fontSize: 11,
          color: "var(--ink3)",
          background: "transparent",
          border: 0,
          cursor: "pointer",
          padding: 0,
        }}
      >
        {anyPending ? (
          <span
            className="pulse-mini"
            style={{ background: "var(--accent)", display: "inline-block", marginRight: 6 }}
          />
        ) : (
          <span className="dot ok" style={{ marginRight: 6 }} />
        )}
        {live && anyPending ? "Running " : "Used "}
        {calls.length} {calls.length === 1 ? "tool" : "tools"}
        {totalMs > 0 ? ` · ${(totalMs / 1000).toFixed(1)}s` : ""} {open ? "▾" : "▸"}
      </button>
      {open && (
        <div
          className="hairline"
          style={{
            marginTop: 8,
            padding: "8px 12px",
            border: "1px solid var(--hairline)",
            borderRadius: 6,
            background: "var(--surface)",
          }}
        >
          {groups.map((g, gi) => (
            <TraceGroupView key={g.label ?? `top-${gi}`} group={g} />
          ))}
        </div>
      )}
    </div>
  );
}

function TraceGroupView({ group }: { group: TraceGroup }) {
  const indented = group.label !== null;
  return (
    <div>
      {group.label !== null && (
        <div
          className="mono"
          style={{
            fontSize: 11.5,
            color: "var(--ink)",
            padding: "4px 0",
            display: "flex",
            alignItems: "center",
            gap: 8,
          }}
        >
          {group.header?.pending ? (
            <span className="pulse-mini" style={{ background: "var(--accent)" }} />
          ) : (
            <span className="dot accent" style={{ width: 6, height: 6 }} />
          )}
          <span style={{ fontWeight: 500 }}>{group.label}</span>
          <span className="chip" style={{ fontSize: 9.5, padding: "0 6px" }}>
            sub-agent
          </span>
        </div>
      )}
      <div style={{ paddingLeft: indented ? 14 : 0 }}>
        {group.tools.map((c, i) => (
          <ToolRow key={i} call={c} />
        ))}
      </div>
    </div>
  );
}

function ToolRow({ call }: { call: LiveTool }) {
  const { tool } = parseToolName(call.name);
  const sources = useMemo(() => extractSources(call), [call]);
  const argStr =
    Object.keys(call.args).length > 0 ? JSON.stringify(call.args) : "";
  return (
    <div>
      <div
        className="mono"
        style={{
          fontSize: 11.5,
          color: "var(--ink2)",
          padding: "4px 0",
          display: "flex",
          alignItems: "center",
          gap: 8,
        }}
      >
        {call.pending ? (
          <span className="pulse-mini" style={{ background: "var(--accent)" }} />
        ) : (
          <span style={{ color: "var(--accent)" }}>→</span>
        )}
        <span style={{ color: "var(--ink)" }}>{tool}</span>
        {argStr && (
          <span
            style={{
              color: "var(--ink3)",
              maxWidth: 240,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
            title={argStr}
          >
            ({argStr})
          </span>
        )}
        <span style={{ marginLeft: "auto", color: "var(--ink3)" }}>
          {call.result_preview ? `${call.result_preview} · ` : ""}
          {call.duration_ms != null ? `${call.duration_ms}ms` : call.pending ? "…" : ""}
        </span>
      </div>
      {sources.length > 0 && (
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 6,
            padding: "2px 0 4px 18px",
          }}
        >
          {sources.map((u) => (
            <a
              key={u}
              href={u}
              target="_blank"
              rel="noreferrer noopener"
              className="chip"
              style={{ fontSize: 10, maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
              title={u}
            >
              {hostOf(u)}
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Pull web-search source URLs from a tool row (web_search / *→web_search).
 * URLs may live in `args` (e.g. an explicit list) or be mentioned in the
 * `result_preview` text. We render whatever we can find.
 */
function extractSources(call: LiveTool): string[] {
  const { tool } = parseToolName(call.name);
  if (tool !== "web_search") return [];
  const found = new Set<string>();
  collectUrls(call.args, found);
  if (call.result_preview) {
    for (const u of call.result_preview.match(URL_RE) ?? []) found.add(u);
  }
  return Array.from(found).slice(0, 6);
}

const URL_RE = /https?:\/\/[^\s"'<>)\]]+/g;

function collectUrls(value: unknown, out: Set<string>): void {
  if (typeof value === "string") {
    for (const u of value.match(URL_RE) ?? []) out.add(u);
  } else if (Array.isArray(value)) {
    for (const v of value) collectUrls(v, out);
  } else if (value && typeof value === "object") {
    for (const v of Object.values(value)) collectUrls(v, out);
  }
}

function hostOf(url: string): string {
  try {
    return new URL(url).host.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function ThinkingIndicator() {
  return (
    <div className="caption" style={{ color: "var(--ink3)", marginTop: 12 }}>
      <span className="pulse-mini" style={{ background: "var(--accent)" }} /> DyPol is
      thinking…
    </div>
  );
}
