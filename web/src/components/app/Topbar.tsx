"use client";

import { useEffect, useRef, useState } from "react";
import { useOrg } from "@/lib/api/OrgContext";
import { goToInstall } from "@/lib/api/useMe";
import type { Route } from "@/lib/app/types";
import { Avatar } from "./Avatar";
import { BellIcon, CalendarIcon, ChevronDownIcon, SearchIcon } from "./icons";

interface Props {
  crumbHere: string;
  onAsk: (question: string) => void;
  onRoute: (route: Route) => void;
}

export function Topbar({ crumbHere, onAsk, onRoute }: Props) {
  const { me, activeOrg, setActiveOrg } = useOrg();
  const [search, setSearch] = useState("");
  const [orgMenuOpen, setOrgMenuOpen] = useState(false);
  const orgMenuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!orgMenuOpen) return;
    const onClick = (e: MouseEvent) => {
      if (!orgMenuRef.current?.contains(e.target as Node)) setOrgMenuOpen(false);
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, [orgMenuOpen]);

  const submitSearch = () => {
    const v = search.trim();
    if (!v) return;
    if (v.includes("?") || v.length > 30) {
      onRoute("ask");
      setTimeout(() => onAsk(v), 200);
      setSearch("");
    }
  };

  const userInitials = (me.user.name ?? me.user.login ?? "??")
    .split(/\s+/)
    .map((s) => s[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <header className="topbar">
      <div className="crumb" ref={orgMenuRef} style={{ position: "relative" }}>
        <button
          type="button"
          onClick={() => setOrgMenuOpen((v) => !v)}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 4,
            background: "transparent",
            border: 0,
            padding: 0,
            color: "inherit",
            cursor: "pointer",
            font: "inherit",
          }}
          aria-haspopup="listbox"
          aria-expanded={orgMenuOpen}
        >
          <span>{activeOrg ?? "—"}</span>
          <ChevronDownIcon />
        </button>
        <span className="sep">/</span>
        <span className="here">{crumbHere}</span>

        {orgMenuOpen && (
          <div
            className="surface hairline"
            style={{
              position: "absolute",
              top: "calc(100% + 8px)",
              left: 0,
              minWidth: 240,
              borderRadius: 6,
              boxShadow: "0 16px 40px -12px rgb(20 17 13 / 0.25)",
              zIndex: 30,
              overflow: "hidden",
            }}
            role="listbox"
          >
            <div
              className="label-tight"
              style={{ padding: "10px 12px 6px" }}
            >
              Switch installation
            </div>
            {me.installations.map((i) => (
              <button
                key={i.install_id}
                type="button"
                onClick={() => {
                  setActiveOrg(i.account_login);
                  setOrgMenuOpen(false);
                }}
                style={{
                  display: "flex",
                  width: "100%",
                  textAlign: "left",
                  padding: "9px 12px",
                  gap: 8,
                  alignItems: "center",
                  background:
                    i.account_login === activeOrg
                      ? "var(--hairline)"
                      : "transparent",
                  border: 0,
                  cursor: "pointer",
                  font: "inherit",
                  color: "var(--ink)",
                }}
              >
                <span
                  className="dot"
                  style={{
                    background:
                      i.account_login === activeOrg
                        ? "var(--accent)"
                        : "var(--ink3)",
                  }}
                />
                <div style={{ flex: 1 }}>
                  <div className="mono text-[13px]">{i.account_login}</div>
                  <div
                    className="mono"
                    style={{ fontSize: 10.5, color: "var(--ink3)" }}
                  >
                    {i.account_type ?? "—"}
                    {i.mode === "public" ? " · public" : ""}
                  </div>
                </div>
              </button>
            ))}
            <button
              type="button"
              onClick={goToInstall}
              className="hairline"
              style={{
                display: "block",
                width: "100%",
                textAlign: "left",
                padding: "10px 12px",
                borderTop: "1px solid var(--hairline)",
                background: "transparent",
                cursor: "pointer",
                font: "inherit",
                color: "var(--ink2)",
                fontSize: 12.5,
              }}
            >
              + Install on another org…
            </button>
          </div>
        )}
      </div>

      <div className="search">
        <SearchIcon style={{ color: "var(--ink3)" }} />
        <input
          type="text"
          placeholder="Search devs, repos, or ask a question…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              submitSearch();
            }
          }}
        />
        <span className="kbd">⌘K</span>
      </div>

      <button type="button" className="iconbtn" title="Notifications">
        <BellIcon />
      </button>
      <button type="button" className="week-pill">
        <CalendarIcon />
        Live
      </button>
      {me.user.avatar_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={me.user.avatar_url}
          alt={me.user.login}
          width={28}
          height={28}
          style={{ borderRadius: "50%" }}
        />
      ) : (
        <Avatar initials={userInitials} color={1} />
      )}
    </header>
  );
}
