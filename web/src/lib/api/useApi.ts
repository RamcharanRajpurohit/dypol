"use client";

/**
 * Tiny in-process fetch cache + dedup hook for view data.
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
 * Why not SWR/React Query: keeping the dependency footprint tight while
 * the project is still single-tenant local. Easy swap later.
 */
import { useEffect, useRef, useState } from "react";
import { ApiError } from "./client";
import { useOrgOptional } from "./OrgContext";

const DEFAULT_TTL_MS = 60_000; // 60s — covers tab switches without thrash
const cache = new Map<string, { value: unknown; at: number }>();
const inflight = new Map<string, Promise<unknown>>();

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
  const fullKey =
    key === null ? null : `${orgCtx?.activeOrg ?? "_"}::${key}`;

  const initial = fullKey ? (cache.get(fullKey)?.value as T | undefined) : undefined;
  const [data, setData] = useState<T | null>(initial ?? null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(!initial && enabled && !!fullKey);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [bumper, setBumper] = useState(0);

  // Latest fetcher in a ref so we don't refetch when callers pass new closures.
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  useEffect(() => {
    if (!enabled || !fullKey) return;
    let cancelled = false;

    const cached = cache.get(fullKey);
    const isFresh = cached && Date.now() - cached.at < ttlMs;

    if (cached) {
      setData(cached.value as T);
      setLoading(false);
    } else {
      setLoading(true);
    }
    if (isFresh && bumper === 0) return; // no need to refetch

    if (cached) setRefreshing(true);

    let promise = inflight.get(fullKey) as Promise<T> | undefined;
    if (!promise) {
      promise = fetcherRef.current();
      inflight.set(fullKey, promise);
      promise.finally(() => inflight.delete(fullKey));
    }

    promise
      .then((value) => {
        if (cancelled) return;
        cache.set(fullKey, { value, at: Date.now() });
        setData(value);
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError) setError(`${err.status}: ${err.message}`);
        else setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
        setRefreshing(false);
      });

    return () => {
      cancelled = true;
    };
  }, [fullKey, enabled, ttlMs, bumper]);

  return {
    data,
    error,
    loading,
    refreshing,
    refresh: () => {
      if (fullKey) cache.delete(fullKey);
      setBumper((n) => n + 1);
    },
  };
}

/** Manual cache invalidation for cross-view writes. */
export function invalidateAll(): void {
  cache.clear();
}

/** Clear cache for a specific key prefix. Useful on org switch boundaries. */
export function invalidatePrefix(prefix: string): void {
  for (const k of [...cache.keys()]) {
    if (k.includes(prefix)) cache.delete(k);
  }
}
