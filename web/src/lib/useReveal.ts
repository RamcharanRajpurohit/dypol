"use client";

import { useEffect } from "react";

export function useScrollReveal(selector = ".reveal, .stagger") {
  useEffect(() => {
    const targets = document.querySelectorAll<HTMLElement>(selector);
    if (!targets.length) return;

    if (typeof IntersectionObserver === "undefined") {
      targets.forEach((el) => el.classList.add("in"));
      return;
    }

    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add("in");
            io.unobserve(entry.target);
          }
        }
      },
      { threshold: 0.12, rootMargin: "0px 0px -8% 0px" },
    );
    targets.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, [selector]);
}
