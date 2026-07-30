"use client";

import { logout } from "@/lib/api";
import { useOrg } from "@/lib/api/OrgContext";
import { OrgPicker } from "@/components/auth/OrgPicker";

interface Props {
  visible: boolean;
}

export function ProfileView({ visible }: Props) {
  const { me, activeOrg, setActiveOrg } = useOrg();

  if (!visible) return null;

  const onLogout = async () => {
    try {
      await logout();
    } catch {
      // ignore
    }
    window.location.href = "/";
  };

  const initials = (me.user.name ?? me.user.login)
    .split(/\s+/)
    .map((s) => s[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <div className="container-app">
      <h1 className="h-page mb-2">Profile</h1>
      <p className="text-[13.5px]" style={{ color: "var(--ink2)" }}>
        Your account, GitHub installations, and active workspace.
      </p>

      {/* ── User card ─────────────────────────────────────────── */}
      <section className="mt-8">
        <div className="card p-6 flex items-center gap-5">
          {me.user.avatar_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={me.user.avatar_url}
              alt={me.user.login}
              width={72}
              height={72}
              style={{ borderRadius: "50%" }}
            />
          ) : (
            <div
              style={{
                width: 72,
                height: 72,
                borderRadius: "50%",
                background: "var(--hairline)",
                color: "var(--ink2)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 24,
                fontWeight: 500,
              }}
            >
              {initials}
            </div>
          )}
          <div style={{ flex: 1 }}>
            <div className="display" style={{ fontSize: 22, lineHeight: 1.15 }}>
              {me.user.name ?? me.user.login}
            </div>
            <div
              className="mono mt-1"
              style={{ fontSize: 12, color: "var(--ink3)" }}
            >
              @{me.user.login}
              {me.user.email ? ` · ${me.user.email}` : ""}
            </div>
          </div>
          <a
            href={`https://github.com/${me.user.login}`}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-secondary"
          >
            View on GitHub →
          </a>
        </div>
      </section>

      {/* ── KPI strip ─────────────────────────────────────────── */}
      <section className="mt-10">
        <div className="grid gap-6 md:grid-cols-3">
          <Kpi label="Active workspace" value={activeOrg ?? "—"} mono />
          <Kpi label="Total installations" value={me.installations.length} />
          <Kpi
            label="Session"
            value="Active"
            sub="Signed-cookie session, 14-day expiry"
          />
        </div>
      </section>

      {/* ── Installations list ────────────────────────────────── */}
      <section className="mt-10">
        <h2 className="h-section mb-1">Connected installations</h2>
        <p className="text-[12.5px]" style={{ color: "var(--ink3)", marginBottom: 12 }}>
          Click an installation to switch the active workspace.
        </p>
        <div className="card overflow-hidden">
          {me.installations.length === 0 && (
            <div className="text-ink2 px-4 py-4 text-[13px]">
              No installations yet. Connect one below.
            </div>
          )}
          {me.installations.map((inst) => {
            const isActive = inst.account_login === activeOrg;
            return (
              <button
                key={inst.install_id}
                type="button"
                onClick={() => setActiveOrg(inst.account_login)}
                className="row w-full text-left"
                style={{
                  gridTemplateColumns: "14px 1fr auto auto",
                  gap: 14,
                  padding: "13px 18px",
                  cursor: "pointer",
                  background: isActive ? "var(--hairline)" : "transparent",
                }}
              >
                <span
                  className="dot"
                  style={{
                    background: isActive ? "var(--accent)" : "var(--ink3)",
                  }}
                />
                <div>
                  <div className="mono text-[13.5px]" style={{ color: "var(--ink)" }}>
                    {inst.account_login}
                  </div>
                  <div
                    className="mono"
                    style={{ fontSize: 11, color: "var(--ink3)", marginTop: 2 }}
                  >
                    {inst.account_type ?? "—"} ·{" "}
                    {inst.mode === "public"
                      ? "Public read-only"
                      : inst.repository_selection === "selected"
                      ? "Selected repos"
                      : "All repositories"}
                  </div>
                </div>
                <span
                  className="mono text-[11px]"
                  style={{ color: "var(--ink3)" }}
                >
                  {inst.mode === "public"
                    ? "public"
                    : `install #${inst.install_id}`}
                </span>
                <span
                  className="text-[12px]"
                  style={{ color: isActive ? "var(--accent)" : "var(--ink2)" }}
                >
                  {isActive ? "Active" : "Switch →"}
                </span>
              </button>
            );
          })}
        </div>
      </section>

      {/* ── Connect another ───────────────────────────────────── */}
      <section className="mt-10">
        <h2 className="h-section mb-1">Connect another account</h2>
        <p className="text-[12.5px]" style={{ color: "var(--ink3)", marginBottom: 14 }}>
          Add a personal account or organization where DyPol should read GitHub data.
        </p>
        <OrgPicker onChanged={() => window.location.reload()} />
      </section>

      {/* ── Account actions ───────────────────────────────────── */}
      <section className="mt-10 mb-12">
        <h2 className="h-section mb-3">Account</h2>
        <div className="flex flex-wrap gap-2">
          <a
            href="https://github.com/settings/profile"
            target="_blank"
            rel="noopener noreferrer"
            className="btn-secondary"
          >
            Manage GitHub profile
          </a>
          <button type="button" className="btn-secondary" onClick={onLogout}>
            Sign out
          </button>
        </div>
      </section>
    </div>
  );
}

function Kpi({
  label,
  value,
  sub,
  mono,
}: {
  label: string;
  value: string | number;
  sub?: string;
  mono?: boolean;
}) {
  return (
    <div className="card p-5">
      <div className="label-tight mb-2">{label}</div>
      <div
        className={mono ? "mono" : undefined}
        style={{
          fontSize: 22,
          fontWeight: 500,
          color: "var(--ink)",
          lineHeight: 1.2,
        }}
      >
        {value}
      </div>
      {sub && (
        <p className="mt-2 text-[12px]" style={{ color: "var(--ink3)" }}>
          {sub}
        </p>
      )}
    </div>
  );
}
