"use client";

import { getAlerts } from "@/lib/api";
import { useApi } from "@/lib/api/useApi";
import { RowSkeleton } from "../Skeleton";

interface Props {
  visible: boolean;
}

export function AlertsView({ visible }: Props) {
  const { data: alerts, error, loading } = useApi(
    visible ? "alerts" : null,
    () => getAlerts(200),
    { ttlMs: 60_000 },
  );

  if (!visible) return null;

  return (
    <div className="container-app">
      <h1 className="h-page mb-2">Alerts</h1>
      <p className="text-[13.5px]" style={{ color: "var(--ink2)" }}>
        Stuck PRs, failing checks, Dependabot, and code-scanning findings.
      </p>

      {loading && !alerts && (
        <div className="card mt-8 overflow-hidden">
          <RowSkeleton />
          <RowSkeleton />
          <RowSkeleton />
        </div>
      )}

      {error && (
        <div className="card mt-8 px-4 py-4 text-[13px]" style={{ color: "var(--hot)" }}>
          Error: {error}
        </div>
      )}

      {alerts && alerts.length === 0 && (
        <div className="card mt-8 max-w-2xl p-6">
          <p className="ai-prose">
            No active alerts.{" "}
            <span className="muted">
              Healthy week. We'll surface stuck PRs, failing checks, and security findings here as
              they appear.
            </span>
          </p>
        </div>
      )}

      {alerts && alerts.length > 0 && (
        <div className="card mt-8">
          {alerts.map((alert, i) => (
            <div
              key={`${alert.repo}-${alert.kind}-${alert.ref}-${i}`}
              className="row"
              style={{
                gridTemplateColumns: "14px 1fr auto auto",
                gap: 14,
                padding: "13px 18px",
              }}
            >
              <span className={`dot ${severityToStatus(alert.severity)}`} />
              <span>
                <span className="mono text-[12px]" style={{ color: "var(--ink3)" }}>
                  [{kindLabel(alert.kind)}]
                </span>{" "}
                <span className="mono text-[12.5px]">{alert.repo}</span>{" "}
                <span style={{ color: "var(--ink2)" }}>{alert.title}</span>
              </span>
              <span className="mono text-[11px]" style={{ color: "var(--ink3)" }}>
                {alert.ref}
              </span>
              <a
                href={alert.url}
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
      )}
    </div>
  );
}

function severityToStatus(sev: string): "ok" | "hot" | "stuck" | "neutral" {
  if (sev === "critical" || sev === "high") return "hot";
  if (sev === "medium") return "stuck";
  return "neutral";
}

function kindLabel(kind: string): string {
  return kind.replace(/_/g, " ");
}
