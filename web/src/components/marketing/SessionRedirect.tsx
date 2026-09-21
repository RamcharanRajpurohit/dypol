"use client";

import { useEffect } from "react";
import { ApiError, me } from "@/lib/api";

/**
 * Client-side session check for the marketing home page.
 *
 * If a valid session cookie exists (i.e. the user previously logged in and
 * came back to `/`), redirect straight to /dashboard instead of showing the
 * logged-out marketing page. Logged-out visitors never notice this: it's one
 * lightweight request fired after mount, and they simply stay on the page.
 */
export function SessionRedirect() {
  useEffect(() => {
    let cancelled = false;

    me()
      .then(() => {
        // Any successful /auth/me response means the session cookie is valid.
        // (The no-install case is handled by the dashboard's own auth gate.)
        if (!cancelled) window.location.replace("/dashboard");
      })
      .catch((err: unknown) => {
        // 401 → genuinely logged out; stay on the marketing page.
        // Other errors (backend down, network) → stay too; never trap a
        // visitor away from the public page because of a failed check.
        if (!cancelled && !(err instanceof ApiError && err.status === 401)) {
          console.warn("Homepage session check failed:", err);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return null;
}
