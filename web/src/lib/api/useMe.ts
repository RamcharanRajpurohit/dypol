"use client";

import { useEffect, useState } from "react";
import { addPublicWorkspace, ApiError, installUrl, loginUrl, me } from "@/lib/api";
import type { MeResponse } from "@/lib/api";
import { identifyUser, trackOnboarding } from "@/lib/telemetry";

export type AuthState =
  | { kind: "loading" }
  | { kind: "anonymous" }
  | { kind: "authenticated"; me: MeResponse }
  | { kind: "no_install"; me: MeResponse }
  | { kind: "error"; message: string };

/**
 * The default public workspace added on first sign-in when the user has no
 * workspaces yet, so the dashboard isn't empty before they connect GitHub.
 */
export const DEFAULT_WORKSPACE = "supabase";

/** Auto-add is best-effort: cap total wall time so sign-in never hangs. */
const RETRY_DELAYS_MS = [0, 1_500, 5_000];

/**
 * Hook for checking the current user's auth state. Pass `forceSync=true` when
 * returning from the GitHub install flow — the backend then skips its sync
 * throttle and reconciles installations before responding.
 *
 * Distinguishes:
 *   - loading       → still fetching
 *   - anonymous     → 401, redirect to /auth/login
 *   - no_install    → signed in but no workspaces, prompt connect
 *   - authenticated → ready to use the app
 *   - error         → backend down or unexpected
 */
export function useMe(forceSync = false): AuthState {
  const [state, setState] = useState<AuthState>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    loadMeWithDefaultWorkspace(forceSync)
      .then((data) => {
        if (cancelled) return;
        // Tie this browser to the real user in PostHog/Sentry from here on.
        identifyUser(data.user);
        trackOnboarding("signed_in", {
          installations: data.installations.length,
          has_default_workspace_error: Boolean(data.defaultWorkspaceError),
        });
        if (data.installations.length === 0) {
          setState({ kind: "no_install", me: data });
        } else {
          setState({ kind: "authenticated", me: data });
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) {
          setState({ kind: "anonymous" });
        } else {
          setState({
            kind: "error",
            message: err instanceof Error ? err.message : String(err),
          });
        }
      });
    return () => {
      cancelled = true;
    };
    // forceSync is fixed at mount (computed from the install-return URL),
    // so this effect intentionally runs once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return state;
}

async function addDefaultWorkspace(): Promise<void> {
  let lastErr: unknown = null;
  for (const delay of RETRY_DELAYS_MS) {
    if (delay > 0) await new Promise((r) => setTimeout(r, delay));
    try {
      await addPublicWorkspace(DEFAULT_WORKSPACE);
      return;
    } catch (err) {
      lastErr = err;
      // A definitive answer won't change on retry.
      if (
        err instanceof ApiError &&
        (err.status === 404 || err.status === 401 || err.status === 400)
      ) {
        throw err;
      }
    }
  }
  throw lastErr;
}

async function loadMeWithDefaultWorkspace(forceSync = false): Promise<MeResponse> {
  const data = await me({ sync: forceSync || undefined });
  if (data.installations.length > 0) return data;

  // First sign-in: seed a default public workspace so the user lands on a
  // working dashboard instead of an empty connection page. The GitHub probe
  // behind this runs on the shared anonymous budget, so it can transiently
  // fail (403/429) — hence retries. If it still fails we surface WHY on the
  // connection page instead of leaving the user with a mystery empty state
  // (the "supabase isn't set by default and I can't add it" bug).
  try {
    await addDefaultWorkspace();
    trackOnboarding("default_workspace_added", { workspace: DEFAULT_WORKSPACE });
    return await me();
  } catch (err) {
    trackOnboarding("default_workspace_failed", {
      workspace: DEFAULT_WORKSPACE,
      status: err instanceof ApiError ? err.status : undefined,
    });
    // Attach the reason to the me-response so the connection screen can
    // show an actionable message (and a manual retry) instead of silence.
    const reason =
      err instanceof ApiError && err.status === 429
        ? "GitHub's API limit is spent right now (shared anonymous budget, resets hourly). Try again in a few minutes or add a workspace manually below."
        : err instanceof ApiError
          ? `Couldn't add the default ${DEFAULT_WORKSPACE} workspace (${err.status}: ${err.message}). You can add it manually below.`
          : `Couldn't add the default ${DEFAULT_WORKSPACE} workspace. You can add it manually below.`;
    return { ...data, defaultWorkspaceError: reason };
  }
}

export const goToLogin = () => {
  window.location.href = loginUrl();
};

export const goToInstall = () => {
  window.location.href = installUrl();
};
