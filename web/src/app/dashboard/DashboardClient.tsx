"use client";

import { AppShell } from "@/components/app/AppShell";
import { OrgPicker } from "@/components/auth/OrgPicker";
import { OrgProvider, useOrg } from "@/lib/api/OrgContext";
import { goToLogin, useMe } from "@/lib/api/useMe";

/**
 * Auth gate around the AppShell.
 * - loading      → blank shell
 * - anonymous    → redirect to GitHub OAuth (/auth/login)
 * - no_install   → show OrgPicker (lists user's personal + each org with install button)
 * - error        → friendly fallback (most likely backend down)
 * - authenticated → render AppShell wrapped in OrgProvider
 */
export function DashboardClient() {
  const auth = useMe();

  if (auth.kind === "loading") {
    return <CenteredMessage caption="Verifying session" title="One moment…" />;
  }

  if (auth.kind === "anonymous") {
    if (typeof window !== "undefined") goToLogin();
    return <CenteredMessage caption="Redirecting" title="Sign in with GitHub…" />;
  }

  if (auth.kind === "no_install") {
    return (
      <CenteredMessage
        caption="Connect a GitHub account"
        title="Choose a workspace"
      >
        <OrgPicker onChanged={() => window.location.reload()} />
      </CenteredMessage>
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
 * Remounts the AppShell when the active org changes so all views refetch
 * with the new `?org=…` query param baked in by the API client. If for
 * any reason no org is selected yet, render nothing — prevents a flash
 * of "org_required" 400s.
 */
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
