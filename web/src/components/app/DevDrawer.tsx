"use client";

import { useEffect } from "react";
import type { Dev } from "@/lib/app/types";
import { Avatar } from "./Avatar";
import { CloseIcon } from "./icons";

interface Props {
  dev: Dev | null;
  onClose: () => void;
}

export function DevDrawer({ dev, onClose }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const open = dev !== null;

  return (
    <>
      <button
        type="button"
        aria-label="Close drawer"
        className={`drawer-mask ${open ? "open" : ""}`}
        onClick={onClose}
      />
      <aside className={`drawer ${open ? "open" : ""}`} aria-hidden={!open}>
        {dev && (
          <>
            <div className="hairline flex items-center justify-between border-b px-6 py-4">
              <span className="label-tight">Developer profile</span>
              <button type="button" className="iconbtn" onClick={onClose} aria-label="Close">
                <CloseIcon />
              </button>
            </div>
            <div className="scroll" style={{ flex: 1, minHeight: 0 }}>
              <div className="px-6 py-6">
                <DrawerBody dev={dev} />
              </div>
            </div>
          </>
        )}
      </aside>
    </>
  );
}

function DrawerBody({ dev }: { dev: Dev }) {
  const handleNoAt = dev.handle.replace("@", "");
  return (
    <>
      <div className="mb-6 flex items-start justify-between">
        <div className="flex items-start gap-4">
          <Avatar initials={dev.avatar} color={dev.color} size="lg" />
          <div>
            <h2 className="display text-[28px] leading-tight">{dev.name}</h2>
            <p className="text-[12.5px]" style={{ color: "var(--ink2)" }}>
              {dev.role}
            </p>
            <p className="mono mt-1 text-[11px]" style={{ color: "var(--ink3)" }}>
              {dev.handle} · github.com/acme-dev
            </p>
          </div>
        </div>
        <div className="text-right">
          <div className="num text-[44px]" style={{ lineHeight: 1 }}>
            {dev.score}
          </div>
          <div className="mono text-[11px]" style={{ color: "var(--accent)" }}>
            ▲ {dev.delta} this week
          </div>
        </div>
      </div>

      <div className="card mb-6 p-5">
        <div className="label-tight mb-3">Score breakdown</div>
        {(
          [
            ["Impact", dev.impact],
            ["Quality", dev.quality],
            ["Collaboration", dev.collab],
            ["Consistency", dev.consist],
          ] as const
        ).map(([label, value]) => (
          <div key={label} className="bar-row">
            <span className="text-[13px]" style={{ color: "var(--ink2)" }}>
              {label}
            </span>
            <div className="bar-track">
              <div
                className="bar-fill grow-x"
                style={{ width: `${value}%`, transformOrigin: "left" }}
              />
            </div>
            <span className="num text-right">{value}</span>
          </div>
        ))}
        <p
          className="italic-serif mt-5 text-[15px] leading-snug"
          style={{ color: "var(--ink2)" }}
        >
          "{dev.name.split(" ")[0]} consistently ships infrastructure improvements with high test
          coverage. Reviews are substantive but slower than the team median (avg 2.1 days)."
        </p>
      </div>

      <div className="mb-6">
        <div className="label-tight mb-3">Active branches</div>
        <div>
          <div
            className="row"
            style={{ gridTemplateColumns: "1fr auto auto", padding: "9px 0" }}
          >
            <span className="mono text-[12.5px]">{handleNoAt}/feat-usage-meter</span>
            <span className="mono text-[11px]" style={{ color: "var(--ink3)" }}>
              9d · 14 commits
            </span>
            <span className="status-line">
              <span className="dot stuck" /> No PR yet
            </span>
          </div>
          <div
            className="row"
            style={{ gridTemplateColumns: "1fr auto auto", padding: "9px 0" }}
          >
            <span className="mono text-[12.5px]">{handleNoAt}/oauth-pkce</span>
            <span className="mono text-[11px]" style={{ color: "var(--ink3)" }}>
              2d · 6 commits
            </span>
            <span className="status-line">
              <span className="dot accent" /> In review
            </span>
          </div>
        </div>
      </div>

      <div className="mb-6">
        <div className="label-tight mb-3">Merged this week</div>
        <ul className="space-y-2.5 text-[13.5px]">
          <li className="flex gap-3">
            <a className="pill flex-shrink-0">#1247</a>
            <span>
              <span style={{ color: "var(--ink)" }}>PKCE rollout for OAuth.</span>{" "}
              <span style={{ color: "var(--ink2)" }}>
                Final piece of auth modernization — removes the legacy redirect path.
              </span>
            </span>
          </li>
          <li className="flex gap-3">
            <a className="pill flex-shrink-0">#1252</a>
            <span>
              <span style={{ color: "var(--ink)" }}>SSO lockout edge case fix.</span>{" "}
              <span style={{ color: "var(--ink2)" }}>
                Stops loop when refresh token expires mid-flow.
              </span>
            </span>
          </li>
          <li className="flex gap-3">
            <a className="pill flex-shrink-0">#1259</a>
            <span>
              <span style={{ color: "var(--ink)" }}>Stripe webhook retry refactor.</span>{" "}
              <span style={{ color: "var(--ink2)" }}>
                Moves retries onto the queue runner — in flight.
              </span>
            </span>
          </li>
        </ul>
      </div>

      <div className="mb-6 grid grid-cols-2 gap-4">
        <div className="card p-4">
          <div className="label-tight mb-2">Reviews given</div>
          <div className="num text-[28px]">11</div>
          <p className="mt-1 text-[12px]" style={{ color: "var(--ink2)" }}>
            8 substantive · 3 nit
          </p>
        </div>
        <div className="card p-4">
          <div className="label-tight mb-2">Reviews owed</div>
          <div className="num text-[28px]" style={{ color: "var(--hot)" }}>
            5
          </div>
          <p className="mt-1 text-[12px]" style={{ color: "var(--ink2)" }}>
            2 over 48h
          </p>
        </div>
      </div>

      <div className="card p-4" style={{ borderLeft: "2px solid var(--hot)" }}>
        <div className="label-tight mb-1.5">Workload signal</div>
        <p className="text-[13px]" style={{ color: "var(--ink2)" }}>
          Currently{" "}
          <span className="num" style={{ color: "var(--hot)" }}>
            5 open PRs
          </span>{" "}
          +{" "}
          <span className="num" style={{ color: "var(--hot)" }}>
            5 reviews owed
          </span>
          . Above team median. Consider redistributing if it stays elevated through Wednesday.
        </p>
      </div>
    </>
  );
}
