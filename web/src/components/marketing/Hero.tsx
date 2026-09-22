"use client";

import { useEffect, useRef, useState } from "react";

const QUESTION = "What is Aanya working on?";

export function Hero() {
  const heroLeftRef = useRef<HTMLDivElement | null>(null);
  const widgetRef = useRef<HTMLDivElement | null>(null);
  const [typed, setTyped] = useState("");
  const [showAnswer, setShowAnswer] = useState(false);
  const [showCaret, setShowCaret] = useState(true);

  useEffect(() => {
    const id = requestAnimationFrame(() => heroLeftRef.current?.classList.add("in"));
    return () => cancelAnimationFrame(id);
  }, []);

  useEffect(() => {
    let i = 0;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const start = setTimeout(function tick() {
      if (i <= QUESTION.length) {
        setTyped(QUESTION.slice(0, i));
        i += 1;
        timer = setTimeout(tick, 36 + Math.random() * 30);
      } else {
        timer = setTimeout(() => {
          setShowCaret(false);
          setShowAnswer(true);
        }, 380);
      }
    }, 900);
    return () => {
      clearTimeout(start);
      if (timer) clearTimeout(timer);
    };
  }, []);

  const onWidgetMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const el = widgetRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    el.style.setProperty("--mx", `${((e.clientX - r.left) / r.width) * 100}%`);
    el.style.setProperty("--my", `${((e.clientY - r.top) / r.height) * 100}%`);
  };

  return (
    <section className="container-x relative pt-32 pb-20 md:pt-48 md:pb-32">
      <div className="grid grid-cols-12 items-end gap-x-10 gap-y-14">
        <div ref={heroLeftRef} className="stagger col-span-12 lg:col-span-7">
          <div className="mb-8 flex items-center gap-3">
            <span className="caption">DyPol / v0.4 / Private beta</span>
            <span className="rule-x" style={{ flex: 1 }} />
          </div>

          <h1 className="h-display mb-8">
            See what your engineering team is <em>actually</em> doing.
          </h1>

          <p className="text-ink2 mb-10 max-w-[600px] text-[17px] leading-[1.55] sm:text-[18px]">
            DyPol is an AI analyst that reads your GitHub data and source code, then answers any
            question you have about your engineering org &mdash; from{" "}
            <span className="italic-serif">"what did we ship last week"</span> to{" "}
            <span className="italic-serif">"why is the billing PR taking so long."</span>
          </p>

          <div className="mt-12 flex flex-wrap items-center gap-x-3 gap-y-2 md:mt-14">
            <span className="caption">Read-only GitHub App</span>
            <span className="text-ink2">·</span>
            <span className="caption">SOC 2 in progress</span>
            <span className="text-ink2">·</span>
            <span className="caption">No data resold, ever</span>
          </div>
        </div>

        <div className="col-span-12 mt-2 lg:col-span-5 lg:mt-0">
          <div
            ref={widgetRef}
            onMouseMove={onWidgetMove}
            className="cursor-glow bg-surface hairline overflow-hidden rounded-[10px] border"
            style={{
              boxShadow: "0 30px 60px -40px rgb(20 17 13 / 0.18), 0 2px 0 rgb(20 17 13 / 0.02)",
            }}
          >
            <div className="hairline flex items-center justify-between border-b px-4 py-3">
              <div className="flex items-center gap-2">
                <span className="codedot" style={{ background: "#E16D5C" }} />
                <span className="codedot" style={{ background: "#E5B341" }} />
                <span className="codedot" style={{ background: "#7AAE6A" }} />
              </div>
              <div className="text-ink2 mono text-[11px] tracking-wider">ASK DYPOL</div>
              <div className="flex items-center gap-1.5">
                <span className="status-dot" />
                <span className="text-ink2 mono text-[10px] tracking-wider uppercase">live</span>
              </div>
            </div>

            <div className="px-4 py-4 text-[13.5px] leading-relaxed sm:px-5 sm:py-5 sm:text-[14.5px]">
              <div className="mb-4 flex items-baseline gap-2">
                <span className="text-ink2 mono text-[12px] select-none">›</span>
                <span className="mono text-[13.5px]">{typed}</span>
                {showCaret && <span className="caret" />}
              </div>

              <div
                className="text-ink space-y-3"
                style={{
                  opacity: showAnswer ? 1 : 0,
                  transition: "opacity .5s ease",
                }}
              >
                <p>
                  Aanya merged <a className="cite">#1247 · auth/oauth-pkce</a> on Tuesday and is
                  currently deep in <a className="cite">#1259 · billing/stripe-webhook-retries</a>{" "}
                  &mdash; she's pushed 14 commits since Monday but hasn't requested review yet.
                </p>
                <p className="text-ink2">
                  One branch looks stuck:{" "}
                  <span className="mono text-[12.5px]">aanya/feat-usage-meter</span> &mdash; last
                  push 9 days ago, no PR opened. Want me to draft a nudge or summarize the diff?
                </p>
                <div className="flex items-center gap-2 pt-1">
                  <button className="hairline text-ink2 hover:text-ink hover:border-ink mono rounded-full border px-2.5 py-1 text-[11px] tracking-wider uppercase transition-colors">
                    Summarize diff
                  </button>
                  <button className="hairline text-ink2 hover:text-ink hover:border-ink mono rounded-full border px-2.5 py-1 text-[11px] tracking-wider uppercase transition-colors">
                    Open PR
                  </button>
                </div>
              </div>
            </div>

            <div className="hairline flex items-center justify-between border-t bg-[#FBF8F3] px-4 py-3">
              <div className="text-ink2 mono text-[11px]">
                <span className="tabular">02 sources</span> ·{" "}
                <span className="tabular">git + sql</span>
              </div>
              <div className="text-ink2 mono text-[11px]">⌘K to ask</div>
            </div>
          </div>

          <div className="caption mt-4 flex items-center gap-3">
            <span>Real screenshot</span>
            <span className="rule-x" style={{ flex: 1 }} />
            <span>Latency 1.2s</span>
          </div>
        </div>
      </div>
    </section>
  );
}
