"use client";

import { useEffect, useState } from "react";
import { addPublicWorkspace, ApiError, installUrl, loginUrl, me } from "@/lib/api";
import type { MeResponse } from "@/lib/api";

export type AuthState =
  | { kind: "loading" }
  | { kind: "anonymous" }
  | { kind: "authenticated"; me: MeResponse }
  | { kind: "no_install"; me: MeResponse }
  | { kind: "error"; message: string };

/**
 * Hook for checking the current user's auth state.
 *
 * Distinguishes:
 *   - loading       → still fetching
 *   - anonymous     → 401, redirect to /auth/login
 *   - no_install    → signed in but no GitHub App installation, prompt install
 *   - authenticated → ready to use the app
 *   - error         → backend down or unexpected
 */
export function useMe(): AuthState {
  const [state, setState] = useState<AuthState>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    loadMeWithDefaultWorkspace()
      .then((data) => {
        if (cancelled) return;
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
  }, []);

  return state;
}

async function loadMeWithDefaultWorkspace(): Promise<MeResponse> {
  const data = await me();
  if (data.installations.length > 0) return data;

  try {
    await addPublicWorkspace("supabase");
    return me();
  } catch {
    return data;
  }
}

export const goToLogin = () => {
  window.location.href = loginUrl();
};

export const goToInstall = () => {
  window.location.href = installUrl();
};
