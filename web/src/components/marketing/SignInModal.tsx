"use client";

import { useEffect, useRef, useState } from "react";
import { loginUrl } from "@/lib/api";
import { GitHubIcon } from "./icons";

type Step = 1 | 2 | 3;

const TRACE_LINES: ReadonlyArray<readonly [string, string, string]> = [
  ["→", "github.oauth.authorize", "ok"],
  ["→", "workspace.lookup", "ok"],
  ["→", "permissions.verify read:repo", "ok"],
  ["→", "session.issue", "ok"],
];

interface Props {
  open: boolean;
  onClose: () => void;
}

export function SignInModal({ open, onClose }: Props) {
  const [step, setStep] = useState<Step>(1);
  const [traceShown, setTraceShown] = useState(0);
  const [dots, setDots] = useState("");
  const cardRef = useRef<HTMLDivElement | null>(null);
  const timersRef = useRef<Array<ReturnType<typeof setTimeout>>>([]);

  useEffect(() => {
    if (!open) return;
    setStep(1);
    setTraceShown(0);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  useEffect(() => {
    return () => {
      timersRef.current.forEach(clearTimeout);
      timersRef.current = [];
    };
  }, []);

  const startAuth = () => {
    setStep(2);
    setTraceShown(0);

    // Show a quick trace animation, then redirect to the real backend
    // OAuth endpoint. The backend will redirect to GitHub, then back to
    // /auth/callback, then to WEB_BASE_URL/dashboard with a session cookie.
    const queueTraceTick = (index: number) => {
      if (index >= TRACE_LINES.length) {
        const t = setTimeout(() => {
          setStep(3);
          let d = 0;
          const di = setInterval(() => {
            d = (d + 1) % 4;
            setDots(".".repeat(d));
          }, 240);
          const t2 = setTimeout(() => {
            clearInterval(di);
            window.location.href = loginUrl();
          }, 600);
          timersRef.current.push(t2);
        }, 280);
        timersRef.current.push(t);
        return;
      }
      const t = setTimeout(() => {
        setTraceShown((n) => n + 1);
        queueTraceTick(index + 1);
      }, 220 + Math.random() * 150);
      timersRef.current.push(t);
    };

    queueTraceTick(0);
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      role="dialog"
      aria-modal="true"
      aria-labelledby="signin-title"
    >
      <button
        type="button"
        aria-label="Close sign in"
        onClick={onClose}
        className="absolute inset-0 cursor-default"
        style={{
          background: "rgb(20 17 13 / 0.32)",
          backdropFilter: "blur(6px)",
          WebkitBackdropFilter: "blur(6px)",
        }}
      />
      <div
        ref={cardRef}
        className="surface hairline relative w-[440px] max-w-[92vw] overflow-hidden rounded-[10px] border"
        style={{ boxShadow: "0 40px 80px -30px rgb(20 17 13 / 0.35)" }}
      >
        <div className="hairline flex items-center justify-between border-b px-5 py-3.5">
          <div className="flex items-center gap-2">
            <span className="codedot" style={{ background: "#E16D5C" }} />
            <span className="codedot" style={{ background: "#E5B341" }} />
            <span className="codedot" style={{ background: "#7AAE6A" }} />
          </div>
          <div className="text-ink2 mono text-[11px] tracking-wider uppercase">Sign in</div>
          <button
            type="button"
            onClick={onClose}
            className="text-ink2 hover:text-ink mono text-[11px] tracking-wider uppercase"
          >
            esc
          </button>
        </div>

        <div className="px-7 py-8">
          {step === 1 && (
            <div>
              <h3 id="signin-title" className="display mb-2 text-[28px] leading-tight">
                Welcome back.
              </h3>
              <p className="text-ink2 mb-6 text-[14.5px]">
                Sign in with the GitHub account connected to your workspace.
              </p>

              <button
                type="button"
                onClick={startAuth}
                className="bg-ink text-bg flex w-full items-center justify-center gap-2.5 rounded-[5px] py-3 text-[14.5px] font-medium transition-transform hover:translate-y-[-1px]"
              >
                <GitHubIcon width={16} height={16} />
                Continue with GitHub
              </button>

              <div className="my-5 flex items-center gap-3">
                <span className="rule-x" style={{ flex: 1 }} />
                <span className="caption">or</span>
                <span className="rule-x" style={{ flex: 1 }} />
              </div>

              <label className="caption mb-2 block" htmlFor="signin-email">
                Work email
              </label>
              <input
                id="signin-email"
                type="email"
                placeholder="you@company.com"
                defaultValue="alex@acme.dev"
                className="bg-bg hairline focus:border-accent mono w-full rounded-[5px] border px-3.5 py-2.5 text-[14.5px] transition-colors focus:outline-none"
              />
              <button
                type="button"
                onClick={startAuth}
                className="btn-primary mt-3 w-full justify-center"
              >
                Continue with email
              </button>
            </div>
          )}

          {step === 2 && (
            <div>
              <div className="mb-6 flex items-center gap-3">
                <span
                  className="status-dot"
                  style={{
                    background: "#E5B341",
                    boxShadow: "0 0 0 0 rgb(229 179 65 / 0.45)",
                  }}
                />
                <span className="caption">Authenticating</span>
              </div>
              <h3 className="display mb-6 text-[26px] leading-tight">
                Connecting to your workspace…
              </h3>
              <ul className="mono space-y-2.5 text-[12.5px]">
                {TRACE_LINES.slice(0, traceShown).map(([arrow, name, status], i) => (
                  <li
                    key={`${name}-${i}`}
                    className="fade-in"
                    style={{ display: "flex", justifyContent: "space-between" }}
                  >
                    <span>
                      <span style={{ color: "var(--ink2)" }}>{arrow}</span>{" "}
                      <span className="text-ink">{name}</span>
                    </span>
                    <span style={{ color: "var(--accent)" }}>{status}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {step === 3 && (
            <div>
              <div className="mb-6 flex items-center gap-3">
                <div className="status-dot" />
                <span className="caption" style={{ color: "var(--accent)" }}>
                  Redirecting to GitHub
                </span>
              </div>
              <h3 className="display mb-2 text-[28px] leading-tight">Almost there.</h3>
              <p className="text-ink2 mb-1 text-[14.5px]">
                Authorize DyPol on GitHub<span>{dots}</span>
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
