"use client";

import { useEffect, useState } from "react";
import { ApiError, getRepo, getRepoPrs } from "@/lib/api";
import type { PR, Repo } from "@/lib/api";
import type { Route } from "@/lib/app/types";

interface Props {
  visible: boolean;
  repoName: string | null;
  onRoute: (route: Route) => void;
}

export function RepoDetailView({ visible, repoName, onRoute }: Props) {
  const [repo, setRepo] = useState<Repo | null>(null);
  const [prs, setPrs] = useState<PR[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!visible || !repoName) return;
    let cancelled = false;
    setError(null);
    setRepo(null);
    setPrs(null);
    Promise.all([getRepo(repoName), getRepoPrs(repoName, "all", 50)])
      .then(([r, p]) => {
        if (cancelled) return;
        setRepo(r);
        setPrs(p);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError) setError(`${err.status}: ${err.message}`);
        else setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [visible, repoName]);

  if (!visible) return null;

  return (
    <div className="container-app">
      <button
        type="button"
        onClick={() => onRoute("repos")}
        className="mb-5 inline-flex items-center gap-1 text-[12.5px]"
        style={{ color: "var(--ink2)" }}
      >
        <span>←</span> Repos
      </button>

      {error && (
        <p style={{ color: "var(--hot)" }}>Error: {error}</p>
      )}

      {!repoName && (
        <p className="text-ink2">No repo selected. Pick one from the Repos view.</p>
      )}

      {repoName && !repo && !error && (
        <p className="text-ink2">Loading {repoName}…</p>
      )}

      {repo && (
        <>
          <div className="mb-2 flex items-start justify-between">
            <div>
              <h1 className="h-page">
                <span
                  className="mono"
                  style={{ fontSize: 28, color: "var(--ink)", fontWeight: 500 }}
                >
                  {repo.name}
                </span>
              </h1>
              <div className="mt-2 flex items-center gap-3">
                <span className="status-line">
                  <span className={`dot ${repo.status}`} />{" "}
                  {repo.status === "hot"
                    ? "Hot"
                    : repo.status === "stuck"
                    ? "Stuck"
                    : repo.status === "ok"
                    ? "Healthy"
                    : "Maintenance"}
                </span>
                <span style={{ color: "var(--ink3)" }}>·</span>
                <span className="text-[12.5px]" style={{ color: "var(--ink2)" }}>
                  {repo.private ? "Private" : "Public"} · default branch{" "}
                  <span className="mono">{repo.default_branch}</span>
                </span>
                <a
                  href={repo.html_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[12.5px]"
                  style={{ color: "var(--ink2)" }}
                >
                  View on GitHub →
                </a>
              </div>
              {repo.summary && (
                <p className="mt-3 text-[13.5px]" style={{ color: "var(--ink2)" }}>
                  {repo.summary}
                </p>
              )}
            </div>
          </div>

          <div className="mt-10 mb-14 grid grid-cols-2 gap-x-14 gap-y-10 pb-1 md:grid-cols-4">
            <Kpi label="Open PRs" value={repo.open_prs} />
            <Kpi label="Open issues" value={repo.open_issues_count} />
            <Kpi
              label="Last push"
              value={
                repo.pushed_at
                  ? formatRelative(new Date(repo.pushed_at))
                  : "—"
              }
            />
            <Kpi label="Status" value={repo.status} />
          </div>

          <section className="mb-12">
            <div className="mb-3 flex items-end justify-between">
              <h2 className="h-section">Pull requests</h2>
              <span className="label-tight">
                {prs ? `${prs.length} loaded` : "loading"}
              </span>
            </div>
            <div className="card overflow-x-auto sm:overflow-hidden">
              <table className="data w-full sm:w-auto">
                <thead>
                  <tr>
                    <th className="w-[90px]">PR</th>
                    <th>Title</th>
                    <th className="w-[160px]">Author</th>
                    <th className="right w-[100px]">Updated</th>
                    <th className="w-[110px]">State</th>
                  </tr>
                </thead>
                <tbody>
                  {!prs && (
                    <tr>
                      <td colSpan={5} className="text-ink2 px-4 py-4">
                        Loading PRs…
                      </td>
                    </tr>
                  )}
                  {prs && prs.length === 0 && (
                    <tr>
                      <td colSpan={5} className="text-ink2 px-4 py-4">
                        No pull requests yet.
                      </td>
                    </tr>
                  )}
                  {prs?.map((pr) => (
                    <tr key={pr.number}>
                      <td>
                        <a
                          className="pill"
                          href={pr.html_url}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          #{pr.number}
                        </a>
                      </td>
                      <td>{pr.title}</td>
                      <td>{pr.author ?? "—"}</td>
                      <td className="right num">
                        {formatRelative(new Date(pr.updated_at))}
                      </td>
                      <td>
                        <span className="status-line">
                          <span
                            className={`dot ${
                              pr.state === "merged"
                                ? "ok"
                                : pr.state === "closed"
                                ? "neutral"
                                : "accent"
                            }`}
                          />{" "}
                          {pr.state}
                          {pr.draft ? " · draft" : ""}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function Kpi({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="hairline border-b pb-5">
      <div className="label-tight mb-2">{label}</div>
      <div className="kpi-num small">{value}</div>
    </div>
  );
}

function formatRelative(d: Date): string {
  const ms = Date.now() - d.getTime();
  const min = Math.floor(ms / 60_000);
  if (min < 60) return `${min}m`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h`;
  const day = Math.floor(hr / 24);
  if (day < 30) return `${day}d`;
  const mo = Math.floor(day / 30);
  return `${mo}mo`;
}
