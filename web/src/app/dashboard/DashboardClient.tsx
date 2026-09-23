"use client";

import { useCallback, useState } from "react";
import { AppShell } from "@/components/app/AppShell";
import { OrgPicker } from "@/components/auth/OrgPicker";
import { OrgProvider, useOrg } from "@/lib/api/OrgContext";
import { DEFAULT_WORKSPACE, goToLogin, useMe } from "@/lib/api/useMe";
import { addPublicWorkspace, ApiError } from "@/lib/api";
import type { MeResponse } from "@/lib/api/types";
import { trackOnboarding } from "@/lib/telemetry";

/**
 * Auth gate around the AppShell.
 * - loading      → blank shell
 * - anonymous    → redirect to GitHub OAuth (/auth/login)
 * - no_install   → show OrgPicker (lists user's personal + each org with install button)
 * - error        → friendly fallback (most likely backend down)
 * - authenticated → render AppShell wrapped in OrgProvider
 */
export function DashboardClient() {
  // Returning from GitHub's install flow lands on /dashboard with
  // ?installation_id=…&setup_action=install. The install reaches Mongo via
  // webhook (can be missed) or the throttled opportunistic sync — neither
  // guarantees the workspace is visible on the first /auth/me. Force one
  // sync (throttle-free, backend supports ?sync=1) before the first me() so
  // the just-installed workspace shows up immediately.
  const [installReturn] = useState(() => {
    if (typeof window === "undefined") return false;
    const p = new URLSearchParams(window.location.search);
    const isInstall = p.has("installation_id");
    if (isInstall) {
      trackOnboarding("install_returned");
      // Strip the params so a refresh doesn't re-force the sync forever.
      p.delete("installation_id");
      p.delete("setup_action");
      const rest = p.toString();
      window.history.replaceState(
        null,
        "",
        window.location.pathname + (rest ? `?${rest}` : ""),
      );
    }
    return isInstall;
  });

  const auth = useMe(installReturn);

  if (auth.kind === "loading") {
    return <CenteredMessage caption="Verifying session" title="One moment…" />;
  }

  if (auth.kind === "anonymous") {
    if (typeof window !== "undefined") goToLogin();
    return <CenteredMessage caption="Redirecting" title="Sign in with GitHub…" />;
  }

  if (auth.kind === "no_install") {
    return (
      <ConnectWorkspace
        me={auth.me}
        onConnected={() => window.location.reload()}
      />
    );
  }

  if (auth.kind === "error") {
    return (
      <CenteredMessage
        caption="Backend unreachable"
        title="Can't reach the API."
        body={`Make sure the backend is running on the configured URL. (${auth.message})`}
      />
    );
  }

  return (
    <OrgProvider me={auth.me}>
      <ShellWithOrgKey />
    </OrgProvider>
  );
}

/**
 * Connection screen for first-time (or workspace-less) users.
 *
 * If the default-workspace auto-add failed during sign-in (e.g. GitHub's
 * shared anonymous rate limit), say so here with a one-click Retry instead
 * of leaving a mystery empty state — the silent-failure onboarding bug.
 */
function ConnectWorkspace({
  me,
  onConnected,
}: {
  me: MeResponse;
  onConnected: () => void;
}) {
  const [autoAddError, setAutoAddError] = useState<string | null>(
    me.defaultWorkspaceError ?? null,
  );
  const [retrying, setRetrying] = useState(false);

  const retryAutoAdd = useCallback(async () => {
    setRetrying(true);
    setAutoAddError(null);
    try {
      await addPublicWorkspace(DEFAULT_WORKSPACE);
      trackOnboarding("workspace_connected", { via: "default_retry" });
      onConnected();
    } catch (err) {
      setAutoAddError(
        err instanceof ApiError && err.status === 429
          ? "GitHub's API limit is still spent — it resets hourly. You can add a workspace manually below in the meantime."
          : err instanceof Error
            ? `Still couldn't add ${DEFAULT_WORKSPACE}: ${err.message}`
            : `Still couldn't add ${DEFAULT_WORKSPACE}.`,
      );
    } finally {
      setRetrying(false);
    }
  }, [onConnected]);

  return (
    <CenteredMessage
      caption="Connect a GitHub account"
      title="Choose a workspace"
    >
      {autoAddError && (
        <div
          className="card"
          style={{
            marginBottom: 14,
            padding: "12px 14px",
            fontSize: 13,
            textAlign: "left",
            color: "var(--hot)",
            lineHeight: 1.5,
          }}
        >
          {autoAddError}
          <div style={{ marginTop: 10 }}>
            <button
              type="button"
              className="btn-primary btn-primary-sm"
              onClick={retryAutoAdd}
              disabled={retrying}
            >
              {retrying ? "Retrying…" : `Retry adding ${DEFAULT_WORKSPACE}`}
            </button>
          </div>
        </div>
      )}
      <OrgPicker onChanged={onConnected} />
    </CenteredMessage>
  );
}
function ShellWithOrgKey() {
  const { activeOrg } = useOrg();
  if (!activeOrg) {
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <p className="text-ink2">Loading workspace…</p>
      </div>
    );
  }
  return <AppShell key={activeOrg} />;
}

function CenteredMessage({
  caption,
  title,
  body,
  action,
  children,
}: {
  caption: string;
  title: string;
  body?: string;
  action?: { label: string; onClick: () => void };
  children?: React.ReactNode;
}) {
  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--bg)",
        padding: 24,
      }}
    >
      <div style={{ maxWidth: 560, width: "100%", textAlign: "center" }}>
        <div className="caption" style={{ marginBottom: 12 }}>
          {caption}
        </div>
        <h1
          className="display"
          style={{ fontSize: 28, lineHeight: 1.15, marginBottom: 8 }}
        >
          {title}
        </h1>
        {body && (
          <p className="text-ink2" style={{ fontSize: 14.5, marginBottom: 24 }}>
            {body}
          </p>
        )}
        {action && (
          <button type="button" className="btn-primary" onClick={action.onClick}>
            {action.label}
          </button>
        )}
        {children && <div style={{ marginTop: 16 }}>{children}</div>}
      </div>
    </div>
  );
}
