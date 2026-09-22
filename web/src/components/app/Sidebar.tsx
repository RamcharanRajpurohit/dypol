"use client";

import { useEffect, useRef, useState } from "react";
import type { ChatSession } from "@/lib/api";
import { useOrg } from "@/lib/api/OrgContext";
import { goToInstall } from "@/lib/api/useMe";
import type { Route } from "@/lib/app/types";
import { cn } from "@/lib/cn";
import { Avatar } from "./Avatar";
import {
  BarsIcon,
  BellIcon,
  ChatIcon,
  ChevronDownIcon,
  ClockIcon,
  DashboardIcon,
  DigestIcon,
  MoonIcon,
  RepoIcon,
  SunIcon,
} from "./icons";

interface SidebarProps {
  route: Route;
  onRoute: (route: Route) => void;
  chatSessions: ChatSession[];
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
  onNewConversation: () => void;
  onDeleteSession: (id: string) => void;
  isDark: boolean;
  onToggleTheme: () => void;
  /** Whether the off-canvas mobile drawer is open (below lg). */
  drawerOpen?: boolean;
}

interface NavLink {
  route?: Route;
  label: string;
  icon: React.ReactNode;
  rightDot?: boolean;
  elevated?: boolean;
  startsNewChat?: boolean;
}

const OVERVIEW_LINKS: ReadonlyArray<NavLink> = [
  { route: "dashboard", label: "Dashboard", icon: <DashboardIcon /> },
  { route: "digest", label: "Weekly digest", icon: <DigestIcon /> },
  { route: "alerts", label: "Alerts", icon: <BellIcon />, rightDot: true },
  { label: "New chat", icon: <ChatIcon />, elevated: true, startsNewChat: true },
];

const PEOPLE_LINKS: ReadonlyArray<NavLink> = [
  { route: "leaderboard", label: "Developers", icon: <BarsIcon /> },
];

const CODE_LINKS: ReadonlyArray<NavLink> = [
  { route: "repos", label: "Repos", icon: <RepoIcon /> },
  { route: "activity", label: "Recent activity", icon: <ClockIcon /> },
];

export function Sidebar({
  route,
  onRoute,
  chatSessions,
  activeSessionId,
  onSelectSession,
  onNewConversation,
  onDeleteSession,
  isDark,
  onToggleTheme,
  drawerOpen = false,
}: SidebarProps) {
  const { me, activeOrg, setActiveOrg } = useOrg();
  const [workspaceMenuOpen, setWorkspaceMenuOpen] = useState(false);
  const workspaceMenuRef = useRef<HTMLDivElement | null>(null);
  const userInitials = (me.user.name ?? me.user.login)
    .split(/\s+/)
    .map((s) => s[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  useEffect(() => {
    if (!workspaceMenuOpen) return;
    const onClick = (e: MouseEvent) => {
      if (!workspaceMenuRef.current?.contains(e.target as Node)) {
        setWorkspaceMenuOpen(false);
      }
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, [workspaceMenuOpen]);

  const renderItem = (item: NavLink, key: string | number) => (
    <button
      key={key}
      type="button"
      onClick={() => {
        if (item.startsNewChat) {
          onNewConversation();
        } else if (item.route) {
          onRoute(item.route);
        }
      }}
      className={cn(
        "nav-item w-full text-left",
        item.elevated && "elevated",
        item.route && route === item.route && "active",
      )}
    >
      {item.icon}
      <span>{item.label}</span>
      {item.rightDot && <span className="dot" />}
    </button>
  );

  return (
    <aside
      className={cn(
        "sidebar",
        // ≥lg: static grid column. <lg: off-canvas drawer, slid in when open.
        "max-lg:fixed max-lg:inset-y-0 max-lg:left-0 max-lg:z-[70] max-lg:w-[min(300px,86vw)]",
        "max-lg:shadow-[24px_0_48px_-32px_rgb(20_17_13/0.35)]",
        "max-lg:-translate-x-full max-lg:transition-transform max-lg:duration-300 max-lg:ease-[cubic-bezier(0.2,0.7,0.2,1)]",
        drawerOpen && "max-lg:translate-x-0",
      )}
    >
      <div ref={workspaceMenuRef} className="hairline relative border-b px-3 pt-3 pb-3">
        <button
          type="button"
          onClick={() => setWorkspaceMenuOpen((v) => !v)}
          className="flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-[var(--warm-tint)]"
          title="Switch workspace"
          aria-haspopup="listbox"
          aria-expanded={workspaceMenuOpen}
        >
          <Avatar initials={(activeOrg ?? "?").slice(0, 1).toUpperCase()} color={0} rounded="md" />
          <span className="min-w-0 flex-1">
            <span
              className="block truncate text-[13.5px] font-medium"
              style={{ color: "var(--ink)" }}
            >
              {activeOrg ?? "No workspace"}
            </span>
          </span>
          <ChevronDownIcon style={{ color: "var(--ink3)" }} />
        </button>

        {workspaceMenuOpen && (
          <div
            className="surface hairline absolute top-[calc(100%-4px)] right-3 left-3 z-30 overflow-hidden rounded-md"
            style={{ boxShadow: "0 16px 40px -12px rgb(20 17 13 / 0.25)" }}
            role="listbox"
          >
            {me.installations.map((i) => (
              <button
                key={i.install_id}
                type="button"
                onClick={() => {
                  setActiveOrg(i.account_login);
                  setWorkspaceMenuOpen(false);
                }}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px]"
                style={{
                  background: i.account_login === activeOrg ? "var(--hairline)" : "transparent",
                  border: 0,
                  color: "var(--ink)",
                  cursor: "pointer",
                  font: "inherit",
                }}
              >
                <span
                  className="dot"
                  style={{
                    background: i.account_login === activeOrg ? "var(--accent)" : "var(--ink3)",
                  }}
                />
                <span className="truncate">{i.account_login}</span>
              </button>
            ))}
            <button
              type="button"
              onClick={goToInstall}
              className="hairline block w-full px-3 py-2 text-left text-[12.5px]"
              style={{
                borderTop: "1px solid var(--hairline)",
                background: "transparent",
                color: "var(--ink2)",
                cursor: "pointer",
                font: "inherit",
              }}
            >
              Install another workspace
            </button>
          </div>
        )}
      </div>

      <div className="scroll flex-1 overflow-y-auto">
        <div className="nav-group">
          <div className="nav-label label-tight">Overview</div>
          {OVERVIEW_LINKS.map((item, i) => renderItem(item, i))}
        </div>

        <div className="nav-group">
          <div className="nav-label label-tight">People</div>
          {PEOPLE_LINKS.map((item, i) => renderItem(item, i))}
        </div>

        <div className="nav-group">
          <div className="nav-label label-tight">Code</div>
          {CODE_LINKS.map((item, i) => renderItem(item, i))}
        </div>

        <div className="nav-group">
          <div className="nav-label label-tight">Recent conversations</div>

          <div style={{ marginLeft: 0, paddingLeft: 0, borderLeft: 0 }}>
            {chatSessions.length === 0 && (
              <div className="text-ink2" style={{ fontSize: 12, padding: "6px 8px" }}>
                No conversations yet.
              </div>
            )}
            {groupSessionsByRecency(chatSessions).map(([bucketLabel, items]) =>
              items.length === 0 ? null : (
                <div key={bucketLabel}>
                  <div className="conv-bucket-label">{bucketLabel}</div>
                  {items.map((s) => {
                    const isActive = route === "ask" && s.id === activeSessionId;
                    return (
                      <div
                        key={s.id}
                        className={cn("conv mini", isActive && "active")}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 4,
                          paddingRight: 4,
                        }}
                      >
                        <button
                          type="button"
                          onClick={() => onSelectSession(s.id)}
                          className="text-left"
                          style={{
                            flex: 1,
                            background: "transparent",
                            border: 0,
                            padding: "4px 0",
                            cursor: "pointer",
                            color: "inherit",
                            font: "inherit",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                          }}
                          title={s.title}
                        >
                          <span className="t">{s.title}</span>
                        </button>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            if (confirm(`Delete "${s.title}"?`)) onDeleteSession(s.id);
                          }}
                          title="Delete"
                          style={{
                            background: "transparent",
                            border: 0,
                            cursor: "pointer",
                            color: "var(--ink3)",
                            fontSize: 13,
                            padding: 2,
                            opacity: 0.6,
                          }}
                          aria-label={`Delete ${s.title}`}
                        >
                          ×
                        </button>
                      </div>
                    );
                  })}
                </div>
              ),
            )}
          </div>
        </div>
      </div>

      <div className="hairline border-t px-3 pt-2 pb-3">
        <div className="flex items-center gap-2 px-2 py-1.5">
          <button
            type="button"
            onClick={() => onRoute("settings")}
            className={cn(
              "flex min-w-0 flex-1 cursor-pointer items-center gap-2 rounded-md px-0 py-1 text-left transition-colors hover:bg-[var(--warm-tint)]",
              route === "settings" && "bg-[var(--warm-tint)]",
            )}
            title="Open account"
          >
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
            <span className="block min-w-0 truncate text-[13px]" style={{ color: "var(--ink)" }}>
              {me.user.name ?? me.user.login}
            </span>
          </button>
          <button
            type="button"
            className="iconbtn"
            title="Toggle theme"
            onClick={onToggleTheme}
            aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
          >
            {isDark ? <SunIcon /> : <MoonIcon />}
          </button>
        </div>
      </div>
    </aside>
  );
}

// ──────────────────────────────────────────────────────────────────
// Group chat sessions by recency for the sidebar buckets.
// ──────────────────────────────────────────────────────────────────
function groupSessionsByRecency(sessions: ChatSession[]): Array<[string, ChatSession[]]> {
  const pinned: ChatSession[] = [];
  const today: ChatSession[] = [];
  const yesterday: ChatSession[] = [];
  const week: ChatSession[] = [];
  const earlier: ChatSession[] = [];
  const now = Date.now();
  for (const s of sessions) {
    if (s.pinned) {
      pinned.push(s);
      continue;
    }
    const days = (now - new Date(s.updated_at).getTime()) / 86_400_000;
    if (days < 1) today.push(s);
    else if (days < 2) yesterday.push(s);
    else if (days < 7) week.push(s);
    else earlier.push(s);
  }
  return [
    ["Pinned", pinned],
    ["Today", today],
    ["Yesterday", yesterday],
    ["This week", week],
    ["Earlier", earlier],
  ];
}
