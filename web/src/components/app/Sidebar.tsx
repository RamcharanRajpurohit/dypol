"use client";

import type { ChatSession } from "@/lib/api";
import { useOrg } from "@/lib/api/OrgContext";
import type { Route } from "@/lib/app/types";
import { cn } from "@/lib/cn";
import { Avatar } from "./Avatar";
import {
  BarsIcon,
  BellIcon,
  ChatIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  ClockIcon,
  DashboardIcon,
  DigestIcon,
  MoonIcon,
  PeopleIcon,
  PlusIcon,
  RepoIcon,
  SettingsIcon,
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
}

interface NavLink {
  route: Route;
  label: string;
  icon: React.ReactNode;
  rightDot?: boolean;
  elevated?: boolean;
}

const OVERVIEW_LINKS: ReadonlyArray<NavLink> = [
  { route: "dashboard", label: "Dashboard", icon: <DashboardIcon /> },
  { route: "digest", label: "Weekly digest", icon: <DigestIcon /> },
  { route: "alerts", label: "Alerts", icon: <BellIcon />, rightDot: true },
  { route: "ask", label: "Ask anything", icon: <ChatIcon />, elevated: true },
];

const PEOPLE_LINKS: ReadonlyArray<NavLink> = [
  { route: "leaderboard", label: "Leaderboard", icon: <BarsIcon /> },
  { route: "leaderboard", label: "All devs", icon: <PeopleIcon /> },
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
}: SidebarProps) {
  const { me, activeOrg } = useOrg();
  const activeInstall = me.installations.find(
    (i) => i.account_login === activeOrg,
  );
  const userInitials = (me.user.name ?? me.user.login)
    .split(/\s+/)
    .map((s) => s[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  const renderItem = (item: NavLink, key: string | number) => (
    <button
      key={key}
      type="button"
      onClick={() => onRoute(item.route)}
      className={cn(
        "nav-item w-full text-left",
        item.elevated && "elevated",
        route === item.route && "active",
      )}
    >
      {item.icon}
      <span>{item.label}</span>
      {item.rightDot && <span className="dot" />}
    </button>
  );

  return (
    <aside className="sidebar">
      <div className="hairline border-b px-3 pt-3 pb-3">
        <button
          type="button"
          onClick={() => onRoute("settings")}
          className="hover:bg-[var(--warm-tint)] flex w-full items-center gap-2.5 rounded-md px-2 py-2 text-left transition-colors"
          title="Workspace settings"
        >
          <Avatar
            initials={(activeOrg ?? "?").slice(0, 1).toUpperCase()}
            color={0}
            rounded="md"
          />
          <span className="min-w-0 flex-1">
            <span
              className="block truncate text-[13.5px] font-medium"
              style={{ color: "var(--ink)" }}
            >
              {activeOrg ?? "No workspace"}
            </span>
            <span
              className="mono block text-[10.5px]"
              style={{ color: "var(--ink3)", letterSpacing: ".04em" }}
            >
              {activeInstall
                ? `${activeInstall.account_type ?? "—"} · ${
                    activeInstall.mode === "public"
                      ? "public read-only"
                      : activeInstall.repository_selection === "selected"
                      ? "selected repos"
                      : "all repos"
                  }`
                : "Pick a workspace"}
            </span>
          </span>
          <ChevronDownIcon style={{ color: "var(--ink3)" }} />
        </button>
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
          <div className="nav-label label-tight flex items-center justify-between">
            <span>Recent conversations</span>
            <button
              type="button"
              title="New conversation"
              onClick={onNewConversation}
              className="iconbtn"
              style={{ width: 20, height: 20 }}
            >
              <PlusIcon />
            </button>
          </div>

          <div style={{ marginLeft: 0, paddingLeft: 0, borderLeft: 0 }}>
            {chatSessions.length === 0 && (
              <div
                className="text-ink2"
                style={{ fontSize: 12, padding: "6px 8px" }}
              >
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
                            if (confirm(`Delete "${s.title}"?`))
                              onDeleteSession(s.id);
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

        <div className="nav-group">
          <div className="nav-label label-tight">Workspace</div>
          {renderItem(
            { route: "settings", label: "Settings", icon: <SettingsIcon /> },
            "settings",
          )}
        </div>
      </div>

      <div className="hairline border-t px-3 pt-2 pb-3">
        <button
          type="button"
          onClick={() => onRoute("profile")}
          className={cn(
            "hover:bg-[var(--warm-tint)] flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-left transition-colors",
            route === "profile" && "bg-[var(--warm-tint)]",
          )}
          title="Open profile"
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
          <span className="min-w-0 flex-1">
            <span
              className="block truncate text-[13px]"
              style={{ color: "var(--ink)" }}
            >
              {me.user.name ?? me.user.login}
            </span>
            <span
              className="mono block text-[10.5px]"
              style={{ color: "var(--ink3)", letterSpacing: ".04em" }}
            >
              @{me.user.login}
            </span>
          </span>
          <ChevronUpIcon style={{ color: "var(--ink3)" }} />
        </button>
        <div className="mt-2 flex items-center justify-between px-2">
          <span
            className="mono flex items-center gap-1.5 text-[10px]"
            style={{
              color: "var(--ink3)",
              letterSpacing: ".08em",
              textTransform: "uppercase",
            }}
          >
            <span className="pulse-mini" style={{ background: "var(--ok)" }} />
            v1.0 · operational
          </span>
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
function groupSessionsByRecency(
  sessions: ChatSession[],
): Array<[string, ChatSession[]]> {
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
