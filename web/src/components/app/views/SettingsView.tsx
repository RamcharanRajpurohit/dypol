"use client";

import { useEffect, useState } from "react";
import { ApiError, getMembers, getOrgInfo, logout } from "@/lib/api";
import type { Member } from "@/lib/api";
import { OrgPicker } from "@/components/auth/OrgPicker";

interface Props {
  visible: boolean;
}

interface OrgInfo {
  org: string;
  account_type: string;
  user_login: string;
}

export function SettingsView({ visible }: Props) {
  const [orgInfo, setOrgInfo] = useState<OrgInfo | null>(null);
  const [members, setMembers] = useState<Member[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!visible) return;
    let cancelled = false;
    setError(null);
    Promise.all([getOrgInfo(), getMembers()])
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
  }, [visible]);

  const onLogout = async () => {
    try {
      await logout();
    } catch {
      // ignore
    }
    window.location.href = "/";
  };

  if (!visible) return null;

  return (
    <div className="container-app">
      <h1 className="h-page mb-2">Settings</h1>
      <p className="text-[13.5px]" style={{ color: "var(--ink2)" }}>
        Workspace, GitHub installation, account.
      </p>

      {error && (
        <p style={{ color: "var(--hot)" }} className="mt-4">
          Error: {error}
        </p>
      )}

      <div className="mt-8 grid gap-6 md:grid-cols-3">
        <div className="card p-5">
          <div className="label-tight mb-2">Active installation</div>
          <div className="kpi-num small mono" style={{ fontSize: 18 }}>
            {orgInfo?.org ?? "…"}
          </div>
          <p className="mt-2 text-[12.5px]" style={{ color: "var(--ink2)" }}>
            {orgInfo
              ? `${orgInfo.account_type} account · read-only`
              : "Loading…"}
          </p>
        </div>
        <div className="card p-5">
          <div className="label-tight mb-2">Members</div>
          <div className="kpi-num small">{members?.length ?? "…"}</div>
          <p className="mt-2 text-[12.5px]" style={{ color: "var(--ink2)" }}>
            {members && members.length === 0
              ? "Personal accounts have no org members."
              : "Visible to the GitHub App installation."}
          </p>
        </div>
        <div className="card p-5">
          <div className="label-tight mb-2">Signed in as</div>
          <div className="kpi-num small mono" style={{ fontSize: 18 }}>
            @{orgInfo?.user_login ?? "…"}
          </div>
          <p className="mt-2 text-[12.5px]" style={{ color: "var(--ink2)" }}>
            Session managed by signed cookie.
          </p>
        </div>
      </div>

      <section className="mt-10">
        <h2 className="h-section mb-3">Connect a GitHub account</h2>
        <p className="text-[13.5px]" style={{ color: "var(--ink2)", marginBottom: 14 }}>
          Install DyPol on your personal account or any organization you belong to.
        </p>
        <OrgPicker onChanged={() => window.location.reload()} />
      </section>

      <section className="mt-10">
        <h2 className="h-section mb-3">Actions</h2>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn-secondary" onClick={onLogout}>
            Sign out
          </button>
        </div>
      </section>

      {members && members.length > 0 && (
        <section className="mt-10">
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
                <div>
                  <div className="text-[13.5px]">{m.name ?? m.login}</div>
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
                  Profile →
                </a>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
