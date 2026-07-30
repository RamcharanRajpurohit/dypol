"use client";

import { useEffect, useRef, useState } from "react";
import {
  createChatSession,
  deleteChatSession,
  listChatSessions,
} from "@/lib/api";
import type { ChatSession } from "@/lib/api";
import { useOrg } from "@/lib/api/OrgContext";
import { ROUTE_TITLES } from "@/lib/app/data";
import type { Dev, Route } from "@/lib/app/types";
import { useTheme } from "@/lib/app/useTheme";
import { DevDrawer } from "./DevDrawer";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { ActivityView } from "./views/ActivityView";
import { AlertsView } from "./views/AlertsView";
import { ChatView, type ChatViewHandle } from "./views/ChatView";
import { DashboardView } from "./views/DashboardView";
import { DigestView } from "./views/DigestView";
import { LeaderboardView } from "./views/LeaderboardView";
import { ProfileView } from "./views/ProfileView";
import { RepoDetailView } from "./views/RepoDetailView";
import { ReposView } from "./views/ReposView";
import { SettingsView } from "./views/SettingsView";

export function AppShell() {
  const { activeOrg } = useOrg();
  const [route, setRoute] = useState<Route>("dashboard");
  const [drawerDev, setDrawerDev] = useState<Dev | null>(null);
  const [selectedRepo, setSelectedRepo] = useState<string | null>(null);
  const [, setActiveQuestion] = useState<string | null>(null);

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
        // Auto-select the most-recent session if user lands on Ask.
        const first = s[0];
        if (first && !activeSessionId) {
          setActiveSessionId(first.id);
        }
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeOrg]);

  const onRoute = (next: Route) => {
    setRoute(next);
    if (scrollRootRef.current) scrollRootRef.current.scrollTop = 0;
  };

  const onAsk = (question: string) => {
    setRoute("ask");
    setActiveQuestion(question);
    // Open a fresh session for the kicked-off question
    void newChat().then(() => {
      setTimeout(() => askRef.current?.ask(question), 150);
    });
  };

  const onSelectSession = (id: string) => {
    setActiveSessionId(id);
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
      <div className="app-shell">
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
        />

        <section className="main-col relative">
          <Topbar
            crumbHere={ROUTE_TITLES[route] ?? "Dashboard"}
            onAsk={onAsk}
            onRoute={onRoute}
          />

          <div ref={scrollRootRef} className="scroll" style={{ position: "relative" }}>
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
            <ProfileView visible={route === "profile"} />
          </div>
        </section>
      </div>

      <DevDrawer dev={drawerDev} onClose={() => setDrawerDev(null)} />
    </>
  );
}
