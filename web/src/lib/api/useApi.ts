"use client";

/**
 * React Query wrapper for view data.
 *
 * Goals (production-grade):
 *  1. **No over-fetching.** A view that's been opened recently is shown
 *     from cache; we don't refetch on every tab switch.
 *  2. **Dedup in flight.** Two views asking for the same key share one
 *     request.
 *  3. **Org-aware.** Cache key includes the active org so switching
 *     workspaces always pulls fresh data for the new org.
 *  4. **Skeleton-friendly.** Distinguishes "loading" (no cached data) from
 *     "revalidating" (have stale data, refreshing in background).
 *
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef } from "react";
import { ApiError } from "./client";
import { useOrgOptional } from "./OrgContext";
import { getApiQueryClient } from "./QueryProvider";

const DEFAULT_TTL_MS = 60_000; // 60s — covers tab switches without thrash

export interface UseApiOptions {
  /** Skip fetching (e.g. when view isn't visible). */
  enabled?: boolean;
  /** How long cached data stays "fresh" — within this window we don't refetch. */
  ttlMs?: number;
}

export interface UseApiState<T> {
  data: T | null;
  error: string | null;
  /** True when there's no data yet — show skeleton. */
  loading: boolean;
  /** True when we have data but are refreshing in background. */
  refreshing: boolean;
  /** Force a refetch ignoring TTL. */
  refresh: () => void;
}

/**
 * Cache and dedup an async data fetcher under ``key``.
 * The active org is automatically appended to the key so switching orgs
 * never serves stale data from another workspace.
 */
export function useApi<T>(
  key: string | null,
  fetcher: () => Promise<T>,
  opts: UseApiOptions = {},
): UseApiState<T> {
  const { enabled = true, ttlMs = DEFAULT_TTL_MS } = opts;
  const orgCtx = useOrgOptional();
  const queryClient = useQueryClient();
  const org = orgCtx?.activeOrg ?? "_";
  const active = enabled && key !== null;
  const queryKey = ["api", org, key] as const;

  // Latest fetcher in a ref so we don't refetch when callers pass new closures.
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const query = useQuery<T, unknown>({
    queryKey,
    queryFn: () => fetcherRef.current(),
    enabled: active,
    staleTime: ttlMs,
  });

  const data = query.data ?? null;
  const error =
    query.error instanceof ApiError
      ? `${query.error.status}: ${query.error.message}`
      : query.error instanceof Error
        ? query.error.message
        : query.error
          ? String(query.error)
          : null;

  return {
    data,
    error,
    loading: active && !data && query.isFetching,
    refreshing: !!data && query.isFetching,
    refresh: () => {
      void queryClient.invalidateQueries({ queryKey });
    },
  };
}

/** Manual cache invalidation for cross-view writes. */
export function invalidateAll(): void {
  void getApiQueryClient()?.invalidateQueries({ queryKey: ["api"] });
}

/** Clear cache for a specific key prefix. Useful on org switch boundaries. */
export function invalidatePrefix(prefix: string): void {
  void getApiQueryClient()?.invalidateQueries({
    predicate: (query) =>
      query.queryKey.some(
        (part) => typeof part === "string" && part.includes(prefix),
      ),
  });
}
