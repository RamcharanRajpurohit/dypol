const KPIS = [
  { label: "Cycle time", value: "3.4", unit: "d", delta: "▲ 0.6 vs prev" },
  { label: "Deploy freq", value: "12.1", unit: "/wk", delta: "▼ 1.4 vs prev" },
  { label: "PR throughput", value: "47", unit: "", delta: "▲ 8 vs prev" },
  { label: "Review latency", value: "11", unit: "h", delta: "▲ 2h vs prev" },
] as const;

export function ShiftSection() {
  return (
    <section id="shift" className="container-x reveal hairline border-t py-20 md:py-36">
      <div className="mb-16 grid grid-cols-12 gap-x-10">
        <div className="col-span-12 lg:col-span-3">
          <div className="eyebrow">01 / The shift</div>
        </div>
        <div className="col-span-12 lg:col-span-9">
          <h2 className="h-section">
            Every other tool gives you a dashboard.
            <br />
            We give you an <em>analyst</em>.
          </h2>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-x-10 gap-y-12">
        <div className="col-span-12 lg:col-span-5">
          <div className="mb-6 flex items-baseline justify-between">
            <div className="caption">Dashboards</div>
            <div className="text-ink2 mono tabular text-[11px]">last 7 days</div>
          </div>

          <div
            className="bg-surface hairline rounded-[8px] border p-5 sm:p-7"
            style={{ boxShadow: "0 1px 0 rgb(20 17 13 / 0.02)" }}
          >
            <div className="grid grid-cols-2 gap-x-4 gap-x-6 gap-y-6 sm:gap-y-8">
              {KPIS.map((kpi) => (
                <div key={kpi.label}>
                  <div className="caption mb-2">{kpi.label}</div>
                  <div className="display tabular text-[34px] leading-none sm:text-[44px]">
                    {kpi.value}
                    {kpi.unit && (
                      <span className="text-ink2 text-[17px] sm:text-[22px]">{kpi.unit}</span>
                    )}
                  </div>
                  <div className="text-ink2 mono tabular mt-1 text-[11px]">{kpi.delta}</div>
                </div>
              ))}
            </div>
            <div className="hairline text-ink2 mono mt-8 border-t pt-6 text-[11.5px] leading-relaxed">
              {"// You: now what?"}
              <br />
              {"// Dashboard:  …"}
            </div>
          </div>
        </div>

        <div className="col-span-12 lg:col-span-7 lg:pt-12">
          <div className="mb-6 flex items-baseline justify-between">
            <div className="caption" style={{ color: "var(--accent)" }}>
              DyPol
            </div>
            <div className="text-ink2 mono text-[11px]">a conversation, not a chart</div>
          </div>

          <div className="space-y-5">
            <div className="border-l-2 pl-4 sm:pl-5" style={{ borderColor: "var(--ink)" }}>
              <div className="caption mb-1.5">Founder</div>
              <p className="text-ink mono text-[13.5px] sm:text-[14px]">
                Why is deploy frequency down this week?
              </p>
            </div>

            <div className="border-l-2 pl-4 sm:pl-5" style={{ borderColor: "var(--accent)" }}>
              <div className="caption mb-1.5" style={{ color: "var(--accent)" }}>
                DyPol
              </div>
              <p className="text-[15.5px] leading-relaxed sm:text-[16px]">
                Two reasons. First, the staging cluster was down Tues–Wed (
                <a className="cite">incident #84</a>) and four PRs that were ready couldn't ship.
                Second, <span className="mono text-[13.5px]">billing-svc</span> has had only one
                reviewer this week because Marcus is on PTO &mdash; that repo accounts for ~40% of
                normal volume. It should normalize Monday.
              </p>
            </div>

            <div className="border-l-2 pl-4 sm:pl-5" style={{ borderColor: "var(--ink)" }}>
              <div className="caption mb-1.5">Founder</div>
              <p className="text-ink mono text-[13.5px] sm:text-[14px]">Show me the four PRs.</p>
            </div>

            <div className="border-l-2 pl-4 sm:pl-5" style={{ borderColor: "var(--accent)" }}>
              <div className="caption mb-1.5" style={{ color: "var(--accent)" }}>
                DyPol
              </div>
              <p className="text-[15.5px] leading-relaxed sm:text-[16px]">
                <a className="cite">#1234</a> <a className="cite">#1238</a>{" "}
                <a className="cite">#1241</a> <a className="cite">#1245</a> &mdash; all green, all
                approved, deploying now that staging is healthy. The first one is a 4-line copy fix;
                want me to start there?
              </p>
            </div>
          </div>

          <div className="caption mt-8">Same data. Different interface.</div>
        </div>
      </div>
    </section>
  );
}
