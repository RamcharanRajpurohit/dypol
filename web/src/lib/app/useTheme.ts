"use client";

import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "pulse-theme";

export function useTheme() {
  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    let dark = false;
    try {
      dark = localStorage.getItem(STORAGE_KEY) === "dark";
    } catch {
      // localStorage not available — fall back to light.
    }
    if (dark) document.documentElement.classList.add("dark");
    setIsDark(dark);
  }, []);

  const toggle = useCallback(() => {
    const next = !document.documentElement.classList.contains("dark");
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem(STORAGE_KEY, next ? "dark" : "light");
    } catch {
      // ignore
    }
    setIsDark(next);
  }, []);

  return { isDark, toggle };
}
