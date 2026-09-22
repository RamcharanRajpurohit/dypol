"use client";

import { useEffect, useRef, useState } from "react";
import { createChatSession, deleteChatSession, listChatSessions } from "@/lib/api";
import type { ChatSession } from "@/lib/api";
import { useOrg } from "@/lib/api/OrgContext";
import type { Dev, Route } from "@/lib/app/types";
import { useTheme } from "@/lib/app/useTheme";
import { cn } from "@/lib/cn";
import { DefaultWorkspaceNotice } from "./DefaultWorkspaceNotice";
import { DevDrawer } from "./DevDrawer";
import { Sidebar } from "./Sidebar";
import { ActivityView } from "./views/ActivityView";
import { AlertsView } from "./views/AlertsView";
import { ChatView, type ChatViewHandle } from "./views/ChatView";
import { DashboardView } from "./views/DashboardView";
import { DigestView } from "./views/DigestView";
import { LeaderboardView } from "./views/LeaderboardView";
import { RepoDetailView } from "./views/RepoDetailView";
import { ReposView } from "./views/ReposView";
import { SettingsView } from "./views/SettingsView";

export function AppShell() {
  const { activeOrg } = useOrg();
  const [route, setRoute] = useState<Route>("dashboard");
  const [drawerDev, setDrawerDev] = useState<Dev | null>(null);
  const [selectedRepo, setSelectedRepo] = useState<string | null>(null);
  const [, setActiveQuestion] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // ── Chat session state — owned by AppShell so the sidebar can render it.
  const [chatSessions, setChatSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);

  const askRef = useRef<ChatViewHandle | null>(null);
  const scrollRootRef = useRef<HTMLDivElement | null>(null);
  const { isDark, toggle } = useTheme();

  useEffect(() => {
    document.documentElement.setAttribute("data-app", "true");
    document.body.setAttribute("data-app", "true");
    return () => {
      document.documentElement.removeAttribute("data-app");
      document.body.removeAttribute("data-app");
    };
  }, []);

  // Close the mobile sidebar drawer on Escape and lock body scroll
  // while it's open (the sidebar itself scrolls internally).
  useEffect(() => {
    if (!sidebarOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSidebarOpen(false);
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [sidebarOpen]);

  // Load sessions whenever the workspace changes.
  //
  // Waits for `activeOrg` and passes it explicitly. This effect belongs to a
  // CHILD of <OrgProvider>, and React runs child effects before parent ones —
  // so under StrictMode's double-invoke the provider had momentarily cleared
  // the module-level default org, this fetch went out without one, the backend
  // answered 400 `org_required` (the user has >1 workspace), and the error was
  // swallowed — leaving the conversation list silently empty.
  useEffect(() => {
    if (!activeOrg) return;
    let cancelled = false;
    listChatSessions(false, activeOrg)
      .then((s) => {
        if (cancelled) return;
        setChatSessions(s);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        // Don't fail silently again — an empty sidebar should never be the
        // only symptom of a broken request.
        console.error("Failed to load chat sessions:", err);
      });
    return () => {
      cancelled = true;
    };
  }, [activeOrg]);

  const onRoute = (next: Route) => {
    setRoute(next);
    setSidebarOpen(false);
    if (scrollRootRef.current) scrollRootRef.current.scrollTop = 0;
  };

  const onSelectSession = (id: string) => {
    setActiveSessionId(id);
    setSidebarOpen(false);
    setRoute("ask");
  };

  const newChat = async () => {
    try {
      const s = await createChatSession();
      setChatSessions((prev) => [s, ...prev]);
      setActiveSessionId(s.id);
      askRef.current?.reset();
      setRoute("ask");
    } catch {
      // ignore for now
    }
  };

  const onDeleteSession = async (id: string) => {
    try {
      await deleteChatSession(id);
    } catch {
      // ignore
    }
    setChatSessions((prev) => prev.filter((s) => s.id !== id));
    if (activeSessionId === id) {
      setActiveSessionId(null);
    }
  };

  const handleSessionCreated = (s: ChatSession) => {
    setChatSessions((prev) => [s, ...prev.filter((p) => p.id !== s.id)]);
    setActiveSessionId(s.id);
  };

  const handleSessionUpdated = (s: ChatSession) => {
    setChatSessions((prev) => {
      const others = prev.filter((p) => p.id !== s.id);
      return [s, ...others];
    });
  };

  return (
    <>
      {/* Shell: 240px sidebar + fluid column ≥lg; below that a top bar with
          a hamburger plus the sidebar as an off-canvas drawer behind a dimmed
          mask. All layout is Tailwind — only themed surfaces live in CSS. */}
      <div className="relative z-[2] flex h-screen flex-col lg:grid lg:grid-cols-[240px_1fr]">
        {/* Mobile-only topbar: hamburger + workspace name. Hidden ≥lg. */}
        <div
          className={cn(
            "z-30 flex h-12 flex-none items-center gap-1.5 border-b px-2 lg:hidden",
            "border-hairline bg-bg dark:bg-[#100d0a]",
          )}
        >
          <button
            type="button"
            className="text-ink2 hover:text-ink grid h-9 w-9 place-items-center rounded-md transition-colors hover:bg-[var(--warm-tint)]"
            onClick={() => setSidebarOpen(true)}
            aria-label="Open navigation menu"
            aria-expanded={sidebarOpen}
          >
            <svg
              width="20"
              height="20"
              viewBox="0 0 20 20"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              aria-hidden
            >
              <path d="M3 6h14" />
              <path d="M3 10h14" />
              <path d="M3 14h14" />
            </svg>
          </button>
          <span className="text-ink2 mono truncate text-[12px] tracking-wider uppercase">
            {activeOrg ?? "DyPol"}
          </span>
        </div>

        <Sidebar
          route={route}
          onRoute={onRoute}
          chatSessions={chatSessions}
          activeSessionId={activeSessionId}
          onSelectSession={onSelectSession}
          onNewConversation={() => void newChat()}
          onDeleteSession={(id) => void onDeleteSession(id)}
          isDark={isDark}
          onToggleTheme={toggle}
          drawerOpen={sidebarOpen}
        />

        {/* Drawer mask (mobile only). */}
        <div
          className={cn(
            "fixed inset-0 z-[65] bg-[rgb(20_17_13/0.32)] backdrop-blur-[2px] transition-opacity duration-200 dark:bg-[rgb(0_0_0/0.55)]",
            sidebarOpen ? "pointer-events-auto opacity-100" : "pointer-events-none opacity-0",
          )}
          onClick={() => setSidebarOpen(false)}
          aria-hidden
        />

        <section className="main-col relative min-h-0 min-w-0 flex-1">
          <div
            ref={scrollRootRef}
            className="scroll relative min-h-0 flex-1 overflow-x-hidden overflow-y-auto"
          >
            <DashboardView visible={route === "dashboard"} onRoute={onRoute} />
            <LeaderboardView visible={route === "leaderboard"} />
            <ReposView
              visible={route === "repos"}
              onSelectRepo={(name) => {
                setSelectedRepo(name);
                onRoute("repo-detail");
              }}
            />
            <RepoDetailView
              visible={route === "repo-detail"}
              repoName={selectedRepo}
              onRoute={onRoute}
            />
            <ChatView
              ref={askRef}
              visible={route === "ask"}
              sessionId={activeSessionId}
              onSessionCreated={handleSessionCreated}
              onSessionUpdated={handleSessionUpdated}
              onActiveQuestionChange={setActiveQuestion}
            />
            <DigestView visible={route === "digest"} />
            <AlertsView visible={route === "alerts"} />
            <ActivityView visible={route === "activity"} />
            <SettingsView visible={route === "settings"} />
          </div>
        </section>
      </div>

      <DefaultWorkspaceNotice onRoute={onRoute} />
      <DevDrawer dev={drawerDev} onClose={() => setDrawerDev(null)} />
    </>
  );
}
