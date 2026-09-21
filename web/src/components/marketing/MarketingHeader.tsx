"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { GitHubIcon } from "./icons";
import { SignInModal } from "./SignInModal";

const NAV_LINKS = [
  { href: "#shift", label: "Product" },
  /* { href: "#pricing", label: "Pricing" }, */
  { href: "#methodology", label: "Methodology" },
  /* { href: "#", label: "Changelog" }, */
] as const;

export function MarketingHeader() {
  const navRef = useRef<HTMLElement | null>(null);
  const [signinOpen, setSigninOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => {
      if (!navRef.current) return;
      navRef.current.classList.toggle("is-floating", window.scrollY > 24);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <>
      <header className="pointer-events-none fixed top-0 right-0 left-0 z-40 flex justify-center">
        <nav
          ref={navRef}
          className="nav pointer-events-auto mx-3 mt-0 flex w-full items-center justify-between rounded-full border border-transparent px-5 py-3 md:mx-6 md:px-7 md:py-3.5"
          style={{ maxWidth: 1240 }}
        >
          <Link href="/" className="display text-[26px] leading-none tracking-tight">
            DyPol
          </Link>

          <ul className="text-ink2 hidden items-center gap-8 text-[14.5px] md:flex">
            {NAV_LINKS.map((link) => (
              <li key={`${link.href}-${link.label}`}>
                <a href={link.href} className="ulink hover:text-ink transition-colors">
                  {link.label}
                </a>
              </li>
            ))}
          </ul>

          <div className="flex items-center gap-5">
            <button
              type="button"
              onClick={() => setSigninOpen(true)}
              className="text-ink2 hover:text-ink hidden text-[14.5px] transition-colors sm:inline-block"
            >
              Sign in
            </button>
            <a href="#cta" className="btn-primary">
              <GitHubIcon />
              Install on GitHub
            </a>
          </div>
        </nav>
      </header>

      <SignInModal open={signinOpen} onClose={() => setSigninOpen(false)} />
    </>
  );
}
