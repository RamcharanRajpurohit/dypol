"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
/* import { GitHubIcon } from "./icons"; */
import { SignInModal } from "./SignInModal";

const NAV_LINKS = [
  { href: "#shift", label: "Product" },
  /* { href: "#pricing", label: "Pricing" }, */
  { href: "#methodology", label: "Methodology" },
  /* { href: "#", label: "Changelog" }, */
] as const;

function MenuIcon({ open }: { open: boolean }) {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      aria-hidden
    >
      {open ? (
        <>
          <path d="M4 4l12 12" />
          <path d="M16 4L4 16" />
        </>
      ) : (
        <>
          <path d="M3 6h14" />
          <path d="M3 10h14" />
          <path d="M3 14h14" />
        </>
      )}
    </svg>
  );
}

export function MarketingHeader() {
  const navRef = useRef<HTMLElement | null>(null);
  const [signinOpen, setSigninOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => {
      if (!navRef.current) return;
      navRef.current.classList.toggle("is-floating", window.scrollY > 24);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // Lock body scroll while the mobile menu is open.
  useEffect(() => {
    if (!menuOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [menuOpen]);

  return (
    <>
      <header className="pointer-events-none fixed top-0 right-0 left-0 z-40 flex justify-center">
        <nav
          ref={navRef}
          className="nav pointer-events-auto mx-3 mt-0 flex w-full items-center justify-between rounded-full border border-transparent px-4 py-3 md:mx-6 md:px-7 md:py-3.5"
          style={{ maxWidth: 1240 }}
        >
          <Link href="/" className="display text-[22px] leading-none tracking-tight sm:text-[26px]">
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

          <div className="flex items-center gap-3 md:gap-5">
            <button
              type="button"
              onClick={() => setSigninOpen(true)}
              className="text-ink hover:text-ink2 inline-block text-[14.5px] transition-colors"
            >
              Sign in
            </button>
            <button
              type="button"
              aria-label={menuOpen ? "Close menu" : "Open menu"}
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((v) => !v)}
              className="text-ink2 hover:text-ink -mr-1 inline-flex h-9 w-9 items-center justify-center transition-colors md:hidden"
            >
              <MenuIcon open={menuOpen} />
            </button>
            {/* <a href="#cta" className="btn-primary">
              <GitHubIcon />
              Install on GitHub
            </a> */}
          </div>
        </nav>
      </header>

      {/* Mobile menu */}
      {menuOpen && (
        <div className="fixed inset-0 z-30 md:hidden" onClick={() => setMenuOpen(false)}>
          <div
            className="fade-in bg-bg absolute inset-x-0 top-0 border-b px-5 pt-20 pb-6"
            style={{
              background: "var(--bg)",
              borderColor: "var(--hairline)",
              boxShadow: "0 24px 40px -30px rgb(20 17 13 / 0.25)",
            }}
          >
            <ul className="flex flex-col divide-y" style={{ borderColor: "var(--hairline)" }}>
              {NAV_LINKS.map((link) => (
                <li key={`${link.href}-${link.label}`}>
                  <a
                    href={link.href}
                    onClick={() => setMenuOpen(false)}
                    className="text-ink block py-3.5 text-[17px] transition-colors"
                  >
                    {link.label}
                  </a>
                </li>
              ))}
            </ul>
            <div className="hairline mt-2 border-t pt-5">
              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false);
                  setSigninOpen(true);
                }}
                className="bg-ink text-bg w-full rounded-[5px] py-3 text-[14.5px] font-medium"
              >
                Sign in
              </button>
            </div>
          </div>
        </div>
      )}

      <SignInModal open={signinOpen} onClose={() => setSigninOpen(false)} />
    </>
  );
}
