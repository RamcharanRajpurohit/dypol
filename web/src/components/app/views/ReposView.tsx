"use client";

import { useState } from "react";
import { getRepos } from "@/lib/api";
import type { Status } from "@/lib/api";
import { useApi } from "@/lib/api/useApi";
import { RowSkeleton } from "../Skeleton";
import { formatPrCount } from "@/lib/app/format";

interface Props {
  visible: boolean;
  onSelectRepo: (name: string) => void;
}

type Filter = "all" | Status;

export function ReposView({ visible, onSelectRepo }: Props) {
  const { data: repos, error, loading } = useApi(
    visible ? "repos" : null,
    () => getRepos(),
    { ttlMs: 5 * 60_000 },
  );
  const [filter, setFilter] = useState<Filter>("all");

  if (!visible) return null;

  const filtered = repos
    ? filter === "all"
      ? repos
      : repos.filter((r) => r.status === filter)
    : [];
  const activeCount = repos?.filter((r) => r.status !== "neutral").length ?? 0;

  return (
    <div className="container-app">
      <div className="mb-8 flex items-end justify-between">
        <div>
          <h1 className="h-page">Repos</h1>
          <p className="mt-2 text-[13.5px]" style={{ color: "var(--ink2)" }}>
            {repos ? (
              <>
                {repos.length} connected · {activeCount} active
              </>
            ) : error ? (
              <span style={{ color: "var(--hot)" }}>Error: {error}</span>
            ) : (
              "Loading…"
            )}
          </p>
        </div>
        <div className="legend">
          <span>
            <span className="dot ok" /> Healthy
          </span>
          <span>
            <span className="dot hot" /> Hot
          </span>
          <span>
            <span className="dot stuck" /> Stuck
          </span>
          <span>
            <span className="dot neutral" /> Maintenance
          </span>
        </div>
      </div>

      <div className="mb-5 flex items-center gap-2">
        {(["all", "hot", "stuck", "ok", "neutral"] as const).map((f) => (
          <button
            key={f}
            type="button"
            className={`chip${filter === f ? " active" : ""}`}
            onClick={() => setFilter(f)}
          >
            {f === "all" ? "All" : f === "ok" ? "Healthy" : f === "neutral" ? "Maintenance" : f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
      </div>

      <div className="card overflow-hidden">
        {loading && !repos && (
          <>
            <RowSkeleton columns={4} />
            <RowSkeleton columns={4} />
            <RowSkeleton columns={4} />
            <RowSkeleton columns={4} />
            <RowSkeleton columns={4} />
          </>
        )}
        {repos && filtered.length === 0 && (
          <div className="text-ink2 px-4 py-6 text-[13px]">
            No repos in this filter.
          </div>
        )}
        {filtered.map((r) => (
          <button
            key={r.full_name}
            type="button"
            onClick={() => onSelectRepo(r.name)}
            className="row w-full text-left"
            style={{
              gridTemplateColumns: "14px 1fr 1.4fr 90px auto",
              gap: 18,
              padding: "14px 18px",
              cursor: "pointer",
            }}
          >
            <span className={`dot ${r.status}`} />
            <div>
              <div
                className="mono text-[14.5px]"
                style={{ color: "var(--ink)", fontWeight: 500 }}
              >
                {r.name}
              </div>
              <div className="text-[11.5px]" style={{ color: "var(--ink3)", marginTop: 2 }}>
                {r.private ? "Private" : "Public"} · {formatPrCount(r)} open PRs
                {r.archived ? " · archived" : ""}
              </div>
            </div>
            <div className="text-[13px]" style={{ color: "var(--ink2)" }}>
              {r.summary || "—"}
            </div>
            <div style={{ height: 24 }} />
            <span className="text-[12px]" style={{ color: "var(--ink2)" }}>
              View →
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
