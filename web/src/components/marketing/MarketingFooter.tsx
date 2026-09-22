const PRODUCT_LINKS = [
  { label: "Overview", href: "#" },
  { label: "Methodology", href: "#methodology" },
  { label: "Pricing", href: "#pricing" },
  { label: "Changelog", href: "#" },
] as const;

const COMPANY_LINKS = [
  { label: "Trust & security", href: "#" },
  { label: "Privacy", href: "#" },
  { label: "Contact", href: "#" },
  { label: "Careers", href: "#" },
] as const;

export function MarketingFooter() {
  return (
    <footer className="container-x hairline border-t pt-16 pb-12">
      <div className="mb-14 flex flex-col gap-10 md:flex-row md:items-end md:justify-between">
        <a href="#" className="display text-[36px] leading-none sm:text-[44px]">
          DyPol
        </a>
        <div className="text-ink2 mono flex items-center gap-2.5 text-[12px] tracking-wider uppercase">
          <span className="status-dot" />
          All systems operational
        </div>
      </div>

      <div className="hairline grid grid-cols-12 gap-x-10 gap-y-10 border-b pb-10">
        <div className="col-span-6 md:col-span-3">
          <div className="caption mb-4">Product</div>
          <ul className="space-y-2.5 text-[15px]">
            {PRODUCT_LINKS.map((link) => (
              <li key={link.label}>
                <a href={link.href} className="ulink text-ink2 hover:text-ink transition-colors">
                  {link.label}
                </a>
              </li>
            ))}
          </ul>
        </div>
        <div className="col-span-6 md:col-span-3">
          <div className="caption mb-4">Company</div>
          <ul className="space-y-2.5 text-[15px]">
            {COMPANY_LINKS.map((link) => (
              <li key={link.label}>
                <a href={link.href} className="ulink text-ink2 hover:text-ink transition-colors">
                  {link.label}
                </a>
              </li>
            ))}
          </ul>
        </div>
        <div className="col-span-12 md:col-span-6 md:text-right">
          <p className="italic-serif text-ink max-w-[460px] text-[20px] leading-[1.3] sm:text-[24px] md:ml-auto">
            Built for the people who actually ship.
            <br />
            Not the people who present about shipping.
          </p>
        </div>
      </div>

      <div className="text-ink2 mono flex flex-col gap-3 pt-8 text-[11.5px] tracking-wider uppercase md:flex-row md:items-center md:justify-between">
        <span>© 2026 DyPol.ai, Inc.</span>
        <span>Made with care, not by committee.</span>
      </div>
    </footer>
  );
}
