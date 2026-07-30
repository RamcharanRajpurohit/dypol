"use client";

import { getActivity } from "@/lib/api";
import { useOrg } from "@/lib/api/OrgContext";
import { useApi } from "@/lib/api/useApi";
import { RowSkeleton } from "../Skeleton";

interface Props {
  visible: boolean;
}

export function ActivityView({ visible }: Props) {
  const { me, activeOrg } = useOrg();
  const isPublic =
    me.installations.find((i) => i.account_login === activeOrg)?.mode === "public";
  const { data: events, error, loading } = useApi(
    visible ? "activity" : null,
    () => getActivity(100),
    { ttlMs: 30_000 },
  );

  if (!visible) return null;

  return (
    <div className="container-app">
      <h1 className="h-page mb-2">Recent activity</h1>
      <p className="text-[13.5px]" style={{ color: "var(--ink2)" }}>
        {isPublic
          ? "Public event timeline, polled from GitHub. Public repos only, refreshed about once a minute."
          : "Webhook-driven event stream from your installed repos."}
      </p>
      <div className="card mt-8">
        {loading && !events && (
          <>
            <RowSkeleton />
            <RowSkeleton />
            <RowSkeleton />
            <RowSkeleton />
          </>
        )}
        {error && (
          <div style={{ color: "var(--hot)" }} className="px-4 py-4 text-[13px]">
            Error: {error}
          </div>
        )}
        {events && events.length === 0 && (
          <div className="text-ink2 px-4 py-4 text-[13px]">
            {isPublic
              ? "No public activity in this account's recent timeline."
              : "No activity yet. Webhooks populate this feed in real time — push, open, or comment on a PR to see it here."}
          </div>
        )}
        {events?.map((e) => (
          <div
            key={e.id}
            className="row"
            style={{ gridTemplateColumns: "28px 1fr auto", gap: 12, padding: "12px 18px" }}
          >
            {e.actor_avatar ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={e.actor_avatar}
                alt={e.actor}
                width={24}
                height={24}
                style={{ borderRadius: "50%" }}
              />
            ) : (
              <div style={{ width: 24, height: 24 }} />
            )}
            <span className="text-[13.5px]">
              <strong style={{ fontWeight: 500 }}>{e.actor}</strong>{" "}
              <span style={{ color: "var(--ink2)" }}>{e.summary}</span>{" "}
              <span className="mono text-[12px]" style={{ color: "var(--ink3)" }}>
                · {e.repo}
              </span>
            </span>
            <span className="mono text-[11px]" style={{ color: "var(--ink3)" }}>
              {formatRelative(new Date(e.created_at))}
            </span>
          </div>
        ))}
      </div>
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
  return `${day}d`;
}
