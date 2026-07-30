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
import type { MeResponse } from "./types";

const STORAGE_KEY = "dypol.activeOrg";

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
    let resolved: string | null = installs[0]?.account_login ?? null;
    if (typeof window !== "undefined") {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored && installs.some((i) => i.account_login === stored)) {
        resolved = stored;
      }
    }
    setDefaultOrg(resolved);
    return resolved;
  });

  // Keep active org in sync if installs list changes underneath us.
  useEffect(() => {
    if (!activeOrg && installs[0]) {
      setActiveOrgState(installs[0].account_login);
    } else if (activeOrg && !installs.some((i) => i.account_login === activeOrg)) {
      setActiveOrgState(installs[0]?.account_login ?? null);
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
