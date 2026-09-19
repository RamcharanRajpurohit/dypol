"use client";

import { getDashboard } from "@/lib/api";
import type { Alert, Contributor, Kpi, Repo } from "@/lib/api";
// Skeleton + helpers below; useApi handles caching & dedup.
import { useOrg } from "@/lib/api/OrgContext";
import { useApi } from "@/lib/api/useApi";
import type { Route } from "@/lib/app/types";
import { KpiSkeleton, RowSkeleton, Skeleton } from "../Skeleton";
import { formatPrCount } from "@/lib/app/format";

interface Props {
  onRoute: (route: Route) => void;
  visible: boolean;
}

export function DashboardView({ onRoute, visible }: Props) {
  const { me } = useOrg();
  const { data, error, loading } = useApi(
    visible ? "dashboard" : null,
    () => getDashboard(),
    { ttlMs: 2 * 60_000 },
  );

  if (!visible) return null;

  if (error) {
    return (
      <div className="container-app">
        <p style={{ color: "var(--hot)" }}>Couldn't load dashboard: {error}</p>
      </div>
    );
  }

  if (loading || !data) {
    return <DashboardSkeleton />;
  }

  const firstName = (me.user.name ?? me.user.login).split(/\s+/)[0];

  return (
    <div className="container-app">
      {/* ── Hero ───────────────────────────────────────────── */}
      <header className="mb-10">
        <div>
          <div className="caption mb-2">
            {data.period_label} · {data.org}
            {data.mode === "public" ? " · public read-only" : ""}
          </div>
          <h1 className="h-page">
            Hi {firstName},{" "}
            <span className="italic-serif">here's the pulse.</span>
          </h1>
          <p
            className="mt-3 text-[14.5px]"
            style={{ color: "var(--ink2)", maxWidth: 640, lineHeight: 1.5 }}
          >
            {data.headline}
          </p>
        </div>
      </header>

      {/* ── KPI strip ──────────────────────────────────────── */}
      <section className="mb-16 grid grid-cols-2 gap-x-12 gap-y-10 md:grid-cols-4">
        {data.kpis.map((kpi) => (
          <KpiCard key={kpi.label} kpi={kpi} />
        ))}
      </section>

      {/* ── Two-column: alerts + contributors ─────────────── */}
      <section className="mb-16 grid grid-cols-1 gap-12 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <SectionHeader
            title="Needs attention"
            sub={
              data.alerts_total === 0
                ? "Healthy week."
                : `${data.alerts_total} active ${
                    data.alerts_total === 1 ? "alert" : "alerts"
                  } · showing top ${data.top_alerts.length}`
            }
            cta={
              data.alerts_total > data.top_alerts.length
                ? { label: "View all", onClick: () => onRoute("alerts") }
                : undefined
            }
          />
          <AlertsList alerts={data.top_alerts} />
        </div>

        <div className="lg:col-span-2">
          <SectionHeader
            title="Who's shipping"
            sub={
              data.top_contributors.length === 0
                ? "No commits yet"
                : `Top ${data.top_contributors.length} · last 7 days`
            }
            cta={{
              label: "Leaderboard",
              onClick: () => onRoute("leaderboard"),
            }}
          />
          <ContributorList contributors={data.top_contributors} />
        </div>
      </section>

      {/* ── Repo health ────────────────────────────────────── */}
      <section className="mb-12">
        <SectionHeader
          title="Repo health"
          sub={`${data.repos_total} ${
            data.repos_total === 1 ? "repo" : "repos"
          } · most recent activity`}
          cta={{ label: "All repos", onClick: () => onRoute("repos") }}
        />
        <RepoGrid repos={data.repos} onRoute={onRoute} />
      </section>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────
// Sub-components
// ──────────────────────────────────────────────────────────────
function SectionHeader({
  title,
  sub,
  cta,
}: {
  title: string;
  sub?: string;
  cta?: { label: string; onClick: () => void };
}) {
  return (
    <div className="mb-4 flex items-end justify-between">
      <div>
        <h2 className="h-section">{title}</h2>
        {sub && (
          <p className="mt-1 text-[12.5px]" style={{ color: "var(--ink3)" }}>
            {sub}
          </p>
        )}
      </div>
      {cta && (
        <button
          type="button"
          className="text-[12.5px]"
          style={{ color: "var(--ink2)" }}
          onClick={cta.onClick}
        >
          {cta.label} →
        </button>
      )}
    </div>
  );
}

function KpiCard({ kpi }: { kpi: Kpi }) {
  const deltaColor =
    kpi.sentiment === "good"
      ? "var(--ok)"
      : kpi.sentiment === "bad"
      ? "var(--hot)"
      : "var(--ink2)";
  const arrow =
    kpi.direction === "up" ? "↑" : kpi.direction === "down" ? "↓" : "—";
  return (
    <div className="hairline border-b pb-5">
      <div className="label-tight mb-3">{kpi.label}</div>
      <div className="kpi-num">
        <span>{Math.round(kpi.value)}</span>
        {kpi.unit && (
          <span style={{ color: "var(--ink3)", fontSize: 14, marginLeft: 6 }}>
            {kpi.unit}
          </span>
        )}
      </div>
      <div className="mono mt-2 text-[11px]" style={{ color: deltaColor }}>
        {kpi.delta_pct !== null
          ? `${arrow} ${Math.abs(kpi.delta_pct)}% vs last week`
          : kpi.direction === "flat"
          ? "— same as last week"
          : "first week of data"}
      </div>
    </div>
  );
}

function AlertsList({ alerts }: { alerts: Alert[] }) {
  if (alerts.length === 0) {
    return (
      <div className="card p-5 text-[13px]" style={{ color: "var(--ink2)" }}>
        No active alerts. We'll surface stuck PRs, failing checks, and
        security findings here as they appear.
      </div>
    );
  }
  return (
    <div className="card overflow-hidden">
      {alerts.map((a, i) => (
        <div
          key={`${a.repo}-${a.kind}-${a.ref}-${i}`}
          className="row"
          style={{
            gridTemplateColumns: "14px 1fr auto auto",
            gap: 14,
            padding: "13px 18px",
          }}
        >
          <span className={`dot ${severityToStatus(a.severity)}`} />
          <span className="text-[13.5px]">
            <span className="mono text-[12.5px]" style={{ color: "var(--ink3)" }}>
              [{a.kind.replace(/_/g, " ")}]
            </span>{" "}
            <span className="mono text-[12.5px]">{a.repo}</span>{" "}
            <span style={{ color: "var(--ink2)" }}>{a.title}</span>
          </span>
          <span className="mono text-[11px]" style={{ color: "var(--ink3)" }}>
            {a.ref}
          </span>
          <a
            href={a.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[12px]"
            style={{ color: "var(--ink2)" }}
          >
            View →
          </a>
        </div>
      ))}
    </div>
  );
}

function ContributorList({
  contributors,
}: {
  contributors: Contributor[];
}) {
  if (contributors.length === 0) {
    return (
      <div className="card p-5 text-[13px]" style={{ color: "var(--ink2)" }}>
        No commits yet in this period.
      </div>
    );
  }
  const max = Math.max(...contributors.map((c) => c.commits), 1);
  return (
    <div className="hairline border-t">
      {contributors.map((c, i) => (
        <div
          key={c.login}
          className="row"
          style={{
            gridTemplateColumns: "22px 28px 1fr auto",
            gap: 12,
            padding: "11px 0",
          }}
        >
          <span className="num text-[12px]" style={{ color: "var(--ink3)" }}>
            {String(i + 1).padStart(2, "0")}
          </span>
          {c.avatar_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={c.avatar_url}
              alt={c.login}
              width={24}
              height={24}
              style={{ borderRadius: "50%" }}
            />
          ) : (
            <div style={{ width: 24, height: 24 }} />
          )}
          <div>
            <div className="text-[13px]" style={{ color: "var(--ink)" }}>
              {c.name ?? c.login}
            </div>
            <div className="mini-track" style={{ marginTop: 4 }}>
              <span
                style={{
                  width: `${Math.min(100, (c.commits / max) * 100)}%`,
                }}
              />
            </div>
          </div>
          <span
            className="num text-[13px]"
            style={{ color: "var(--ink)", minWidth: 36, textAlign: "right" }}
          >
            {c.commits}
            <span
              className="text-[10.5px]"
              style={{ color: "var(--ink3)", marginLeft: 4 }}
            >
              commits
            </span>
          </span>
        </div>
      ))}
    </div>
  );
}

function RepoGrid({
  repos,
  onRoute,
}: {
  repos: Repo[];
  onRoute: (route: Route) => void;
}) {
  if (repos.length === 0) {
    return (
      <div className="card p-5 text-[13px]" style={{ color: "var(--ink2)" }}>
        No repos accessible to this workspace yet.
      </div>
    );
  }
  return (
    <div className="grid gap-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
      {repos.map((r) => (
        <button
          key={r.full_name}
          type="button"
          onClick={() => onRoute("repo-detail")}
          className="surface hairline hover:border-[var(--ink2)] flex flex-col items-start gap-1.5 rounded-md border p-3 text-left transition-colors"
        >
          <div className="flex items-center gap-2 w-full">
            <span className={`dot ${r.status}`} />
            <span
              className="mono text-[12.5px]"
              style={{
                color: "var(--ink)",
                fontWeight: 500,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {r.name}
            </span>
          </div>
          <div className="mono text-[10.5px]" style={{ color: "var(--ink3)" }}>
            {formatPrCount(r)} open PRs · {r.private ? "private" : "public"}
          </div>
          {r.summary && (
            <div
              className="text-[11.5px]"
              style={{
                color: "var(--ink3)",
                overflow: "hidden",
                textOverflow: "ellipsis",
                display: "-webkit-box",
                WebkitLineClamp: 2,
                WebkitBoxOrient: "vertical",
              }}
            >
              {r.summary}
            </div>
          )}
        </button>
      ))}
    </div>
  );
}

function severityToStatus(sev: string): "ok" | "hot" | "stuck" | "neutral" {
  if (sev === "critical" || sev === "high") return "hot";
  if (sev === "medium") return "stuck";
  return "neutral";
}

// ──────────────────────────────────────────────────────────────
// Skeleton — mirrors the real layout so there's no jump on load
// ──────────────────────────────────────────────────────────────
function DashboardSkeleton() {
  return (
    <div className="container-app">
      <header className="mb-10">
        <Skeleton width={140} height={11} style={{ marginBottom: 12 }} />
        <Skeleton width={320} height={32} style={{ marginBottom: 14 }} />
        <Skeleton width={520} height={14} />
      </header>

      <section className="mb-16 grid grid-cols-2 gap-x-12 gap-y-10 md:grid-cols-4">
        <KpiSkeleton />
        <KpiSkeleton />
        <KpiSkeleton />
        <KpiSkeleton />
      </section>

      <section className="mb-16 grid grid-cols-1 gap-12 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <Skeleton width={140} height={16} style={{ marginBottom: 14 }} />
          <div className="card overflow-hidden">
            <RowSkeleton />
            <RowSkeleton />
            <RowSkeleton />
          </div>
        </div>
        <div className="lg:col-span-2">
          <Skeleton width={120} height={16} style={{ marginBottom: 14 }} />
          <div className="hairline border-t">
            {[0, 1, 2, 3, 4].map((i) => (
              <div
                key={i}
                style={{
                  display: "grid",
                  gridTemplateColumns: "22px 28px 1fr auto",
                  gap: 12,
                  padding: "11px 0",
                  alignItems: "center",
                }}
              >
                <Skeleton width={16} height={11} />
                <Skeleton width={24} height={24} rounded={12} />
                <Skeleton width="80%" height={11} />
                <Skeleton width={36} height={11} />
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="mb-12">
        <Skeleton width={120} height={16} style={{ marginBottom: 14 }} />
        <div className="grid gap-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
          {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
            <div
              key={i}
              className="surface hairline border rounded-md p-3"
              style={{ display: "flex", flexDirection: "column", gap: 8 }}
            >
              <Skeleton width="60%" height={11} />
              <Skeleton width="40%" height={9} />
              <Skeleton width="90%" height={9} />
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
