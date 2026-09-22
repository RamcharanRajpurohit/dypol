"use client";

import { useState } from "react";
import { getLeaderboard } from "@/lib/api";
import { useOrg } from "@/lib/api/OrgContext";
import { useApi } from "@/lib/api/useApi";
import { RowSkeleton } from "../Skeleton";

type Period = 7 | 30 | 90;

interface Props {
  visible: boolean;
}

export function LeaderboardView({ visible }: Props) {
  const [days, setDays] = useState<Period>(30);
  const { activeOrg } = useOrg();
  const { data: entries, error, loading } = useApi(
    visible ? `leaderboard:${days}` : null,
    () => getLeaderboard(days, 50, activeOrg ?? undefined),
    { ttlMs: 10 * 60_000 },
  );

  if (!visible) return null;

  return (
    <div className="container-app">
      <div className="mb-8 flex items-end justify-between">
        <div>
          <h1 className="h-page">Developers</h1>
          <p className="mt-2 text-[13.5px]" style={{ color: "var(--ink2)" }}>
            Ranked by commits + PRs merged + reviews. Last {days} days.
          </p>
        </div>
      </div>

      <div className="mb-5 flex items-center gap-3">
        <div className="hairline surface flex items-center gap-1 rounded-md border p-0.5">
          {([7, 30, 90] as const).map((p) => (
            <button
              key={p}
              type="button"
              className={`chip${days === p ? " active" : ""}`}
              style={{ border: 0, padding: "4px 9px" }}
              onClick={() => setDays(p)}
            >
              {p} days
            </button>
          ))}
        </div>
        <span className="label-tight ml-auto">
          {entries
            ? `${entries.length} contributors`
            : error
            ? `Error: ${error}`
            : "Loading…"}
        </span>
      </div>

      <div className="card overflow-x-auto sm:overflow-hidden">
        <table className="data w-full sm:w-auto">
          <thead>
            <tr>
              <th className="w-[56px]">#</th>
              <th>Developer</th>
              <th className="right w-[100px]">Score</th>
              <th className="right w-[80px]">Commits</th>
              <th className="right w-[100px]">PRs merged</th>
              <th className="right w-[80px]">Reviews</th>
            </tr>
          </thead>
          <tbody>
            {loading && !entries && (
              <>
                <tr><td colSpan={6} style={{ padding: 0 }}><RowSkeleton columns={5} /></td></tr>
                <tr><td colSpan={6} style={{ padding: 0 }}><RowSkeleton columns={5} /></td></tr>
                <tr><td colSpan={6} style={{ padding: 0 }}><RowSkeleton columns={5} /></td></tr>
                <tr><td colSpan={6} style={{ padding: 0 }}><RowSkeleton columns={5} /></td></tr>
              </>
            )}
            {entries && entries.length === 0 && (
              <tr>
                <td colSpan={6} className="text-ink2 px-4 py-4">
                  No contributor data yet for this period.
                </td>
              </tr>
            )}
            {entries?.map((e) => (
              <tr key={e.login}>
                <td className="num text-[var(--ink3)]">{String(e.rank).padStart(2, "0")}</td>
                <td>
                  <div className="flex items-center gap-2.5">
                    {e.avatar_url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={e.avatar_url}
                        alt={e.login}
                        width={28}
                        height={28}
                        className="rounded-full"
                      />
                    ) : (
                      <div className="w-7 h-7 rounded-full bg-[var(--ink3)]" />
                    )}
                    <div>
                      <div className="text-[13.5px] text-[var(--ink)]">{e.name ?? e.login}</div>
                      <div className="mono text-[10.5px] text-[var(--ink3)] tracking-wider">
                        @{e.login}
                      </div>
                    </div>
                  </div>
                </td>
                <td className="right">
                  <div className="num text-[18px] text-[var(--ink)]">{e.score}</div>
                  <div className="mini-track ml-auto mt-1">
                    <span
                      style={{
                        width: `${Math.min(100, (e.score / Math.max(...entries.map((x) => x.score), 1)) * 100)}%`,
                      }}
                    />
                  </div>
                </td>
                <td className="right num">{e.commits}</td>
                <td className="right num">{e.prs_merged}</td>
                <td className="right num">{e.reviews}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
