interface Plan {
  name: string;
  meta: string;
  price: string;
  priceUnit?: string;
  cadence: string;
  features: ReadonlyArray<string>;
  recommended?: boolean;
}

const PLANS: ReadonlyArray<Plan> = [
  {
    name: "Free",
    meta: "up to 5 devs",
    price: "$0",
    cadence: "forever",
    features: ["— All eight tools", "— 1 repo", "— 30-day history", "— Community Slack"],
  },
  {
    name: "Startup",
    meta: "Recommended",
    price: "$15",
    priceUnit: " / dev / mo",
    cadence: "billed monthly",
    features: [
      "— Everything in Free",
      "— Unlimited repos",
      "— 12-month history",
      "— Slack & Linear webhooks",
      "— Email support",
    ],
    recommended: true,
  },
  {
    name: "Growth",
    meta: "25+ devs",
    price: "$25",
    priceUnit: " / dev / mo",
    cadence: "SOC 2, SSO, audit log export",
    features: [
      "— Everything in Startup",
      "— SAML SSO",
      "— Custom data retention",
      "— Shared Slack channel",
    ],
  },
];

export function PricingSection() {
  return (
    <section id="pricing" className="container-x reveal hairline border-t py-28 md:py-36">
      <div className="mb-14 grid grid-cols-12 gap-x-10">
        <div className="col-span-12 lg:col-span-3">
          <div className="eyebrow">05 / Pricing</div>
        </div>
        <div className="col-span-12 lg:col-span-9">
          <h2 className="h-section">
            Free for small teams. <em>Honest pricing</em> for the rest.
          </h2>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-x-10 gap-y-10">
        {PLANS.map((plan) => (
          <div
            key={plan.name}
            className={`col-span-12 border-t pt-8 md:col-span-4 ${
              plan.recommended ? "plan-recommended" : "hairline"
            }`}
            style={plan.recommended ? { borderTopWidth: 2 } : undefined}
          >
            <div className="mb-1 flex items-baseline justify-between">
              <h3 className="display text-[28px]">{plan.name}</h3>
              <span
                className="caption"
                style={plan.recommended ? { color: "var(--accent)" } : undefined}
              >
                {plan.meta}
              </span>
            </div>
            <div className="display tabular mt-3 mb-2 text-[44px] leading-none">
              {plan.price}
              {plan.priceUnit && <span className="text-ink2 text-[18px]">{plan.priceUnit}</span>}
            </div>
            <p className="text-ink2 mono mb-6 text-[12px]">{plan.cadence}</p>
            <ul className="text-ink2 space-y-2 text-[15.5px] leading-relaxed">
              {plan.features.map((feature) => (
                <li key={feature}>{feature}</li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <div className="rule-x mt-14" />
      <div className="mt-8 grid grid-cols-12 gap-x-10">
        <div className="col-span-12 md:col-span-7">
          <p className="text-ink2 text-[16.5px]">
            Enterprise (self-host, custom DPA, dedicated support) &mdash;{" "}
            <a href="#" className="ulink text-ink">
              talk to us &rarr;
            </a>
          </p>
        </div>
        <div className="col-span-12 md:col-span-5 md:text-right">
          <p className="mono text-ink2 text-[14px]">
            We undercut LinearB and Swarmia by half. We do this by being independent and not
            sales-led.
          </p>
        </div>
      </div>
    </section>
  );
}
