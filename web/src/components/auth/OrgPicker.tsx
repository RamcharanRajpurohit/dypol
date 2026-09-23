"use client";

import { useEffect, useState } from "react";
import { ApiError, listConnections, loginUrl } from "@/lib/api";
import type { ConnectedAccount } from "@/lib/api";
import { trackOnboarding } from "@/lib/telemetry";
import { OrgSearch } from "./OrgSearch";

/**
 * Lists the user's existing workspaces and offers two ways to add more:
 *
 *  1. **Install the GitHub App** — full access (private + public).
 *     GitHub's own install picker handles account selection.
 *
 *  2. **Search and add a public org** — read-only public-data workspace, no
 *     install. Useful for testing, demos, or analyzing OSS projects.
 */
export function OrgPicker({
  onChanged,
  showConnected = true,
}: {
  onChanged?: () => void;
  showConnected?: boolean;
}) {
  const [connected, setConnected] = useState<ConnectedAccount[] | null>(null);
  const [installUrl, setInstallUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    try {
      const d = await listConnections();
      // Funnel: a previously-empty list gaining its first workspace = the
      // user got connected (manual add or returning from the GitHub install).
      if (connected && connected.length === 0 && d.connected.length > 0) {
        trackOnboarding("workspace_connected", { via: "picker", count: d.connected.length });
      }
      setConnected(d.connected);
      setInstallUrl(d.install_url);
      onChanged?.();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        window.location.href = loginUrl();
        return;
      }
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  useEffect(() => {
    let cancelled = false;
    listConnections()
      .then((d) => {
        if (cancelled) return;
        setConnected(d.connected);
        setInstallUrl(d.install_url);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) {
          window.location.href = loginUrl();
          return;
        }
        setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Poll once after the user has been redirected to GitHub for install,
  // so when the webhook lands we can move on.
  useEffect(() => {
    if (!onChanged || !connected) return;
    const start = connected.length;
    const t = setInterval(async () => {
      try {
        const d = await listConnections();
        if (d.connected.length > start) {
          setConnected(d.connected);
          setInstallUrl(d.install_url);
          onChanged();
          clearInterval(t);
        }
      } catch {
        // ignore
      }
    }, 6000);
    return () => clearInterval(t);
  }, [onChanged, connected]);

  if (error) {
    return <p style={{ color: "var(--hot)" }}>Couldn't load workspaces: {error}</p>;
  }
  if (!connected) {
    return <p className="text-ink2">Loading…</p>;
  }

  return (
    <div style={{ maxWidth: 620, margin: "0 auto" }}>
      <section className="card p-5" style={{ marginBottom: 18 }}>
        <OrgSearch onAdded={refresh} />
      </section>

      {showConnected && connected.length > 0 && (
        <div className="card mb-5" style={{ overflow: "hidden" }}>
          {connected.map((acc) => (
            <ConnectedRow key={`${acc.mode}:${acc.login}`} account={acc} />
          ))}
        </div>
      )}

      {installUrl && (
        <div className="card p-5" style={{ textAlign: "center" }}>
          <a
            href={installUrl}
            className="btn-primary"
            target="_blank"
            rel="noopener noreferrer"
          >
            {connected.length === 0
              ? "Connect a GitHub account"
              : "Connect another account"}
          </a>
        </div>
      )}
    </div>
  );
}

function ConnectedRow({ account }: { account: ConnectedAccount }) {
  const initial = account.login.slice(0, 1).toUpperCase();
  const isPublic = account.mode === "public";
  return (
    <div
      className="row"
      style={{
        gridTemplateColumns: "32px 1fr auto",
        gap: 14,
        padding: "14px 18px",
        textAlign: "left",
      }}
    >
      {account.avatar_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={account.avatar_url}
          alt={account.login}
          width={28}
          height={28}
          style={{ borderRadius: "50%" }}
        />
      ) : (
        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: "50%",
            background: "var(--hairline)",
            color: "var(--ink2)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontWeight: 500,
            fontSize: 13,
          }}
        >
          {initial}
        </div>
      )}
      <div>
        <div className="text-[13.5px]" style={{ color: "var(--ink)" }}>
          {account.login}
        </div>
        <div
          className="mono"
          style={{ fontSize: 11, color: "var(--ink3)", marginTop: 2 }}
        >
          {account.type}
          {isPublic
            ? " · public read-only"
            : ` · ${account.repositories_count} ${
                account.repositories_count === 1 ? "repo" : "repos"
              }${
                account.repository_selection === "selected" ? " (selected)" : ""
              }`}
        </div>
      </div>
      <span
        className="status-line"
        style={{
          color: isPublic ? "var(--ink2)" : "var(--accent)",
          fontSize: 12,
        }}
      >
        <span className={`dot ${isPublic ? "neutral" : "ok"}`} />
        {isPublic ? "Public" : "Connected"}
      </span>
    </div>
  );
}
