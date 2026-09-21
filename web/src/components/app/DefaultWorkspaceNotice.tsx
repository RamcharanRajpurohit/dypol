"use client";

import { useEffect, useState } from "react";
import type { Route } from "@/lib/app/types";

/**
 * One-time popup card shown after login, on the dashboard.
 *
 * Tells the user that the `supabase` workspace is connected by default and
 * that they can connect their own (and other open-source repos) from Settings.
 * Dismissal is persisted in localStorage so it only ever shows once per browser.
 */
export function DefaultWorkspaceNotice({ onRoute }: { onRoute: (r: Route) => void }) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    try {
      if (window.localStorage.getItem("dypol.workspaceNotice.dismissed") !== "1") {
        setOpen(true);
      }
    } catch {
      // localStorage unavailable — still show once per visit, never crash.
      setOpen(true);
    }
  }, []);

  const dismiss = () => {
    setOpen(false);
    try {
      window.localStorage.setItem("dypol.workspaceNotice.dismissed", "1");
    } catch {
      // ignore — persistence is best-effort
    }
  };

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-labelledby="ws-notice-title"
      className="fixed right-5 bottom-5 z-50 w-[360px] max-w-[calc(100vw-40px)]"
    >
      <div className="card hairline relative overflow-hidden border p-5" style={{ boxShadow: "0 24px 48px -20px rgb(20 17 13 / 0.35)" }}>
        <button
          type="button"
          onClick={dismiss}
          aria-label="Dismiss"
          className="text-ink2 hover:text-ink mono absolute top-3 right-3 text-[11px] tracking-wider uppercase"
        >
          esc ✕
        </button>

        <div className="caption mb-2">Heads up</div>
        <h3 id="ws-notice-title" className="display mb-2 text-[18px] leading-snug">
          Supabase is connected by default
        </h3>
        <p className="text-ink2 text-[13px] leading-relaxed">
          Your workspace ships with the <span className="mono" style={{ color: "var(--ink)" }}>supabase</span>{" "}
          repo connected. You can connect your own projects and other open-source
          repos anytime from <strong style={{ color: "var(--ink)" }}>Settings</strong>.
        </p>

        <div className="mt-4 flex gap-2">
          <button
            type="button"
            className="btn-primary btn-primary-sm"
            onClick={() => {
              dismiss();
              onRoute("settings");
            }}
          >
            Open Settings
          </button>
          <button type="button" className="btn-secondary" onClick={dismiss}>
            Got it
          </button>
        </div>
      </div>
    </div>
  );
}
