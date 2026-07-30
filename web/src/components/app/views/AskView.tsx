"use client";

import {
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import { ApiError, ask } from "@/lib/api";
import type { AskAnswer } from "@/lib/api";
import { ArrowSendIcon } from "../icons";

const SUGGESTIONS = [
  "What changed in the last 7 days?",
  "Which PRs are stuck?",
  "Who has been most active?",
  "What's failing CI right now?",
];

export interface AskViewHandle {
  ask: (question: string) => void;
  reset: () => void;
}

interface Props {
  visible: boolean;
  ref?: React.Ref<AskViewHandle>;
  onActiveQuestionChange?: (question: string | null) => void;
}

export function AskView({ visible, ref, onActiveQuestionChange }: Props) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const [headerQ, setHeaderQ] = useState<string>("What would you like to know?");
  const [composer, setComposer] = useState("");
  const [answer, setAnswer] = useState<AskAnswer | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runAsk = useCallback(
    async (q: string) => {
      if (!q.trim() || loading) return;
      setHeaderQ(q);
      onActiveQuestionChange?.(q);
      setLoading(true);
      setError(null);
      setAnswer(null);
      try {
        const result = await ask(q);
        setAnswer(result);
      } catch (err) {
        if (err instanceof ApiError) setError(`${err.status}: ${err.message}`);
        else setError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
        if (scrollRef.current) {
          scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
      }
    },
    [loading, onActiveQuestionChange],
  );

  useImperativeHandle(
    ref,
    () => ({
      ask: (q: string) => void runAsk(q),
      reset: () => {
        setAnswer(null);
        setError(null);
        setHeaderQ("What would you like to know?");
        onActiveQuestionChange?.(null);
        inputRef.current?.focus();
      },
    }),
    [onActiveQuestionChange, runAsk],
  );

  // No auto-question on first reveal — user types or picks a suggestion.
  useEffect(() => {
    if (!visible) return;
    inputRef.current?.focus();
  }, [visible]);

  const autosize = () => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  };

  const submit = () => {
    const v = composer.trim();
    if (!v) return;
    setComposer("");
    void runAsk(v);
    requestAnimationFrame(autosize);
  };

  if (!visible) return null;

  const totalSources =
    answer?.sources.reduce((a, g) => a + g.items.length, 0) ?? 0;

  return (
    <div className="ask-grid" style={{ height: "100%" }}>
      <div
        className="relative"
        style={{ display: "flex", flexDirection: "column", minHeight: 0 }}
      >
        <div ref={scrollRef} className="scroll" style={{ flex: 1 }}>
          <div className="ask-thread">
            <div className="mb-8">
              <div className="label-tight mb-2">Conversation</div>
              <h1 className="h-page">
                <span className="italic-serif" style={{ color: "var(--ink2)" }}>"</span>
                {headerQ}
                <span className="italic-serif" style={{ color: "var(--ink2)" }}>"</span>
              </h1>
            </div>

            {loading && (
              <div className="text-ink2 mono text-[12.5px]">
                <span className="pdot" /> Searching your org…
              </div>
            )}

            {error && (
              <div style={{ color: "var(--hot)" }} className="text-[13px]">
                Error: {error}
              </div>
            )}

            {answer && !loading && (
              <div className="fade-in mb-12">
                <div className="ai-prose mb-5">{answer.answer}</div>

                {answer.followups.length > 0 && (
                  <div className="mb-6 flex flex-wrap gap-1.5">
                    {answer.followups.map((f) => (
                      <button
                        key={f}
                        type="button"
                        className="chip"
                        onClick={() => void runAsk(f)}
                      >
                        {f}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="composer-wrap">
          <form
            className="composer"
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
          >
            <textarea
              ref={inputRef}
              value={composer}
              onChange={(e) => {
                setComposer(e.target.value);
                requestAnimationFrame(autosize);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  submit();
                }
              }}
              placeholder="Ask anything about your engineering org…"
              rows={1}
              disabled={loading}
            />
            <div className="composer-actions">
              <div className="flex flex-wrap items-center gap-2">
                <span className="chip">@ scope: all repos</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="label-tight hidden sm:inline">⏎ to send</span>
                <button type="submit" className="btn-primary-sm" disabled={loading}>
                  Send
                  <ArrowSendIcon />
                </button>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  className="chip"
                  onClick={() => void runAsk(s)}
                  disabled={loading}
                >
                  {s}
                </button>
              ))}
            </div>
          </form>
        </div>
      </div>

      <div className="ask-rail">
        <div className="hairline flex items-center justify-between border-b px-4 pt-4 pb-3">
          <span className="label-tight">Sources</span>
          <span className="mono text-[10.5px]" style={{ color: "var(--ink3)" }}>
            {answer ? `${totalSources} items` : "— items"}
          </span>
        </div>
        <div className="scroll flex-1 overflow-y-auto">
          {!answer && (
            <div
              className="px-4 py-6 text-[12.5px]"
              style={{ color: "var(--ink3)" }}
            >
              Sources will appear here as the agent works.
            </div>
          )}
          {answer?.sources.map((g) => (
            <div key={g.kind}>
              <div className="px-4 pt-4 pb-2 label-tight">{g.kind}</div>
              {g.items.length === 0 && (
                <div
                  className="px-4 pb-3 text-[12px]"
                  style={{ color: "var(--ink3)" }}
                >
                  None.
                </div>
              )}
              {g.items.map((it, i) => (
                <a
                  key={i}
                  href={it.url ?? "#"}
                  target={it.url ? "_blank" : undefined}
                  rel="noopener noreferrer"
                  className="rail-item block"
                  style={{ textDecoration: "none" }}
                >
                  <div
                    className="text-[13px] mono"
                    style={{ color: "var(--ink)", letterSpacing: "-0.005em" }}
                  >
                    {it.t}
                  </div>
                  <div
                    className="text-[11.5px] mt-0.5"
                    style={{ color: "var(--ink3)" }}
                  >
                    {it.d}
                  </div>
                </a>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
