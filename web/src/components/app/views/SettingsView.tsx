"use client";

import { useEffect, useState } from "react";
import { OrgPicker } from "@/components/auth/OrgPicker";
import { ApiError, getMembers, getOrgInfo, logout } from "@/lib/api";
import type { Member } from "@/lib/api";
import { useOrg } from "@/lib/api/OrgContext";

interface Props {
  visible: boolean;
}

interface OrgInfo {
  org: string;
  account_type: string;
  user_login: string;
}

export function SettingsView({ visible }: Props) {
  const { me, activeOrg, setActiveOrg } = useOrg();
  const [orgInfo, setOrgInfo] = useState<OrgInfo | null>(null);
  const [members, setMembers] = useState<Member[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!visible) return;
    let cancelled = false;
    setError(null);
    Promise.all([getOrgInfo(activeOrg ?? undefined), getMembers(activeOrg ?? undefined)])
      .then(([o, m]) => {
        if (cancelled) return;
        setOrgInfo(o as OrgInfo);
        setMembers(m);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError) setError(`${err.status}: ${err.message}`);
        else setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [visible, activeOrg]);

  const onLogout = async () => {
    try {
      await logout();
    } catch {
      // ignore
    }
    window.location.href = "/";
  };

  if (!visible) return null;

  const displayName = me.user.name ?? me.user.login;
  const activeInstall = me.installations.find((i) => i.account_login === activeOrg);

  return (
    <div className="container-app">
      <header className="mb-8 flex flex-wrap items-center justify-between gap-5">
        <div className="flex min-w-0 items-center gap-4">
          {me.user.avatar_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={me.user.avatar_url}
              alt={me.user.login}
              width={56}
              height={56}
              style={{ borderRadius: "50%" }}
            />
          ) : (
            <div
              className="grid place-items-center"
              style={{
                width: 56,
                height: 56,
                borderRadius: "50%",
                background: "var(--hairline)",
                color: "var(--ink2)",
                fontWeight: 600,
              }}
            >
              {displayName.slice(0, 1).toUpperCase()}
            </div>
          )}
          <div className="min-w-0">
            <h1 className="h-page truncate">Account</h1>
            <p className="mono mt-1 truncate text-[12px]" style={{ color: "var(--ink3)" }}>
              {displayName} · @{me.user.login}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <a
            href={`https://github.com/${me.user.login}`}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-secondary"
          >
            GitHub profile
          </a>
          <button type="button" className="btn-secondary" onClick={onLogout}>
            Sign out
          </button>
        </div>
      </header>

      {error && (
        <p style={{ color: "var(--hot)" }} className="mb-6 text-[13px]">
          Error: {error}
        </p>
      )}

      <section className="mb-8 grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        <div>
          <div className="mb-3 flex items-end justify-between">
            <div>
              <h2 className="h-section">Workspaces</h2>
            </div>
          </div>
          <div className="card overflow-hidden">
            {me.installations.map((inst) => {
              const isActive = inst.account_login === activeOrg;
              return (
                <button
                  key={inst.install_id}
                  type="button"
                  onClick={() => setActiveOrg(inst.account_login)}
                  className={`row w-full text-left grid grid-cols-1 sm:grid-cols-[14px_1fr_auto] gap-2 px-4 py-3 sm:gap-3.5 ${isActive ? "bg-[var(--hairline)]" : ""}`}
                >
                  <span className={`dot ${isActive ? "bg-[var(--accent)]" : "bg-[var(--ink3)]"}`} />
                  <div className="min-w-0">
                    <div className="truncate text-[13.5px] text-[var(--ink)]">{inst.account_login}</div>
                    <div className="mono mt-1 text-[11px] text-[var(--ink3)]">{workspaceMeta(inst)}</div>
                  </div>
                  <span className={`text-[12px] ${isActive ? "text-[var(--accent)]" : "text-[var(--ink2)]"}`}>
                    {isActive ? "Active" : "Switch"}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <h2 className="h-section mb-3">Current</h2>
          <div className="card p-5">
            <div className="label-tight mb-2">Active workspace</div>
            <div className="truncate text-[20px]" style={{ color: "var(--ink)", fontWeight: 500 }}>
              {activeOrg ?? orgInfo?.org ?? "..."}
            </div>
            <div className="mt-3 space-y-2 text-[12.5px]" style={{ color: "var(--ink2)" }}>
              <div className="flex justify-between gap-4">
                <span>Type</span>
                <span>{activeInstall?.account_type ?? orgInfo?.account_type ?? "..."}</span>
              </div>
              <div className="flex justify-between gap-4">
                <span>Repos</span>
                <span>{activeInstall ? workspaceScope(activeInstall) : "..."}</span>
              </div>
              <div className="flex justify-between gap-4">
                <span>Members</span>
                <span>{members ? members.length : "..."}</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="mb-8">
        <OrgPicker showConnected={false} onChanged={() => window.location.reload()} />
      </section>

      {members && members.length > 0 && (
        <section className="mb-12">
          <h2 className="h-section mb-3">Members</h2>
          <div className="card overflow-hidden">
            {members.map((m) => (
              <div
                key={m.login}
                className="row"
                style={{
                  gridTemplateColumns: "32px 1fr auto",
                  gap: 12,
                  padding: "12px 18px",
                }}
              >
                {m.avatar_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={m.avatar_url}
                    alt={m.login}
                    width={28}
                    height={28}
                    style={{ borderRadius: "50%" }}
                  />
                ) : (
                  <div style={{ width: 28, height: 28 }} />
                )}
                <div className="min-w-0">
                  <div className="truncate text-[13.5px]">{m.name ?? m.login}</div>
                  <div className="mono text-[11px]" style={{ color: "var(--ink3)" }}>
                    @{m.login}
                  </div>
                </div>
                <a
                  href={m.html_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[12px]"
                  style={{ color: "var(--ink2)" }}
                >
                  GitHub
                </a>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function workspaceMeta(inst: {
  account_type?: string | null;
  mode?: string | null;
  repository_selection?: string | null;
}) {
  return `${inst.account_type ?? "Account"} · ${workspaceScope(inst)}`;
}

function workspaceScope(inst: {
  mode?: string | null;
  repository_selection?: string | null;
}) {
  if (inst.mode === "public") return "public read-only";
  if (inst.repository_selection === "selected") return "selected repos";
  return "all repos";
}
