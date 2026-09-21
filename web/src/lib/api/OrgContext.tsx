"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { setDefaultOrg } from "./client";
import type { Installation, MeResponse } from "./types";

const STORAGE_KEY = "dypol.activeOrg";

/**
 * Pick the default workspace.
 *
 * Preference order:
 *  1. An explicitly stored choice (localStorage) — if still valid, and it
 *     isn't a public/demo workspace masquerading as the default while a real
 *     App install exists (new users used to get stuck on the auto-added
 *     public workspace even after connecting their org).
 *  2. The first real (install-mode) workspace.
 *  3. The first workspace of any kind.
 */
function resolveDefaultOrg(
  installs: Installation[],
  stored: string | null,
): string | null {
  const preferred = installs.find((i) => i.mode !== "public") ?? installs[0] ?? null;
  if (stored) {
    const storedInst = installs.find((i) => i.account_login === stored);
    if (storedInst) {
      const storedIsDemo =
        storedInst.mode === "public" && preferred && preferred.mode !== "public";
      if (!storedIsDemo) return stored;
    }
  }
  return preferred?.account_login ?? null;
}

export interface OrgContextValue {
  me: MeResponse;
  activeOrg: string | null;
  setActiveOrg: (login: string) => void;
}

const OrgContext = createContext<OrgContextValue | null>(null);

export function OrgProvider({
  me,
  children,
}: {
  me: MeResponse;
  children: React.ReactNode;
}) {
  const installs = me.installations;

  // Hydrate from localStorage; fall back to first installation.
  // Set the module-level default synchronously inside the initializer so
  // any API call fired during the first render already carries `?org=…`.
  const [activeOrg, setActiveOrgState] = useState<string | null>(() => {
    const stored =
      typeof window !== "undefined" ? window.localStorage.getItem(STORAGE_KEY) : null;
    const resolved = resolveDefaultOrg(installs, stored);
    setDefaultOrg(resolved);
    return resolved;
  });

  // Keep active org in sync if installs list changes underneath us.
  useEffect(() => {
    if (!activeOrg || !installs.some((i) => i.account_login === activeOrg)) {
      setActiveOrgState(resolveDefaultOrg(installs, null));
    }
  }, [installs, activeOrg]);

  // Push to module-level so api() auto-attaches `?org=...`.
  //
  // No cleanup that resets it to null: this effect re-runs on every org change
  // (and twice on mount under StrictMode), and clearing the default in between
  // left a window where in-flight and child-effect requests went out with no
  // org at all — which 400s for any user with more than one workspace.
  useEffect(() => {
    setDefaultOrg(activeOrg);
  }, [activeOrg]);

  const setActiveOrg = useCallback((login: string) => {
    // Publish synchronously, in the event handler. Child effects fire before
    // the provider's own effect on re-render, so any fetch they start must
    // already see the new org — updating the module default only in an effect
    // sent requests off with the PREVIOUS org (stale-data-after-switch bug).
    setDefaultOrg(login);
    setActiveOrgState(login);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, login);
    }
  }, []);

  const value = useMemo<OrgContextValue>(
    () => ({ me, activeOrg, setActiveOrg }),
    [me, activeOrg, setActiveOrg],
  );

  return <OrgContext.Provider value={value}>{children}</OrgContext.Provider>;
}

export function useOrg(): OrgContextValue {
  const ctx = useContext(OrgContext);
  if (!ctx) {
    throw new Error("useOrg() must be used inside an <OrgProvider>");
  }
  return ctx;
}

/** Read current org without throwing — for components rendered outside provider. */
export function useOrgOptional(): OrgContextValue | null {
  return useContext(OrgContext);
}
