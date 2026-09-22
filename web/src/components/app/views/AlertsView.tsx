"use client";

import { getAlerts } from "@/lib/api";
import { useOrg } from "@/lib/api/OrgContext";
import { useApi } from "@/lib/api/useApi";
import { RowSkeleton } from "../Skeleton";

interface Props {
  visible: boolean;
}

export function AlertsView({ visible }: Props) {
  const { activeOrg } = useOrg();
  const { data: alerts, error, loading } = useApi(
    visible ? "alerts" : null,
    () => getAlerts(200, activeOrg ?? undefined),
    { ttlMs: 2 * 60_000 },
  );

  if (!visible) return null;

  return (
    <div className="container-app">
      <h1 className="h-page mb-8">Alerts</h1>

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
        <div className="card max-w-2xl p-5 text-[13px]" style={{ color: "var(--ink2)" }}>
          No alerts.
        </div>
      )}

      {alerts && alerts.length > 0 && (
        <div className="card">
          {alerts.map((alert, i) => (
            <div
              key={`${alert.repo}-${alert.kind}-${alert.ref}-${i}`}
              className="row grid grid-cols-1 sm:grid-cols-[14px_1fr_auto_auto] gap-2 px-4 py-3 sm:gap-3.5"
            >
              <span className={`dot ${severityToStatus(alert.severity)}`} />
              <span>
                <span className="mono text-[12px] text-[var(--ink3)]">
                  [{kindLabel(alert.kind)}]
                </span>{" "}
                <span className="mono text-[12.5px]">{alert.repo}</span>{" "}
                <span className="text-[var(--ink2)]">{alert.title}</span>
              </span>
              <span className="mono text-[11px] text-[var(--ink3)]">{alert.ref}</span>
              <a
                href={alert.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[12px] text-[var(--ink2)]"
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
