"use client";

import { useState } from "react";
import { getRepos } from "@/lib/api";
import type { Status } from "@/lib/api";
import { useOrg } from "@/lib/api/OrgContext";
import { useApi } from "@/lib/api/useApi";
import { RowSkeleton } from "../Skeleton";
import { formatPrCount } from "@/lib/app/format";

interface Props {
  visible: boolean;
  onSelectRepo: (name: string) => void;
}

type Filter = "all" | Status;

export function ReposView({ visible, onSelectRepo }: Props) {
  const { activeOrg } = useOrg();
  const { data: repos, error, loading } = useApi(
    visible ? "repos" : null,
    () => getRepos(activeOrg ?? undefined),
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
            className="row w-full text-left grid grid-cols-1 sm:grid-cols-[14px_1fr_1.4fr_90px_auto] gap-2 px-4 py-3 sm:gap-4.5"
          >
            <span className={`dot ${r.status}`} />
            <div>
              <div className="mono text-[14.5px] text-[var(--ink)] font-medium">
                {r.name}
              </div>
              <div className="text-[11.5px] text-[var(--ink3)] mt-0.5">
                {r.private ? "Private" : "Public"} · {formatPrCount(r)} open PRs
                {r.archived ? " · archived" : ""}
              </div>
            </div>
            <div className="text-[13px] text-[var(--ink2)]">{r.summary || "—"}</div>
            <div className="h-6" />
            <span className="text-[12px] text-[var(--ink2)]">View →</span>
          </button>
        ))}
      </div>
    </div>
  );
}
