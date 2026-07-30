"use client";

import type { CSSProperties } from "react";

/**
 * Minimal skeleton primitives. Single shimmer animation, theme-aware.
 *
 * Use ``<Skeleton />`` for any pulsing block, or one of the composed
 * pieces (``KpiSkeleton``, ``RowSkeleton``) when you want a full row's
 * worth of placeholder geometry.
 */
export function Skeleton({
  width,
  height = 14,
  rounded = 4,
  style,
}: {
  width?: number | string;
  height?: number | string;
  rounded?: number;
  style?: CSSProperties;
}) {
  return (
    <span
      className="dypol-skeleton"
      style={{
        display: "inline-block",
        width: width ?? "100%",
        height,
        borderRadius: rounded,
        ...style,
      }}
    />
  );
}

export function KpiSkeleton() {
  return (
    <div className="hairline border-b pb-5">
      <div className="mb-3">
        <Skeleton width={90} height={10} />
      </div>
      <div className="mb-2">
        <Skeleton width={70} height={28} />
      </div>
      <Skeleton width={120} height={10} />
    </div>
  );
}

export function RowSkeleton({ columns = 3 }: { columns?: number }) {
  const widths = ["55%", "30%", "20%", "25%"];
  return (
    <div
      className="row"
      style={{
        gridTemplateColumns: `repeat(${columns}, auto) 1fr`,
        gap: 14,
        padding: "13px 18px",
      }}
    >
      <Skeleton width={14} height={14} rounded={7} />
      {Array.from({ length: columns - 1 }).map((_, i) => (
        <Skeleton key={i} width={widths[i] ?? "20%"} height={12} />
      ))}
      <Skeleton width={48} height={12} style={{ justifySelf: "end" }} />
    </div>
  );
}

export function CardSkeleton({ height = 140 }: { height?: number }) {
  return (
    <div
      className="card"
      style={{ padding: 18, height, display: "flex", flexDirection: "column", gap: 10 }}
    >
      <Skeleton width="60%" height={14} />
      <Skeleton width="40%" height={11} />
      <div style={{ flex: 1 }} />
      <Skeleton width="80%" height={10} />
    </div>
  );
}
