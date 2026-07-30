export function ExamplesSection() {
  return (
    <section className="container-x reveal hairline border-t py-28 md:py-36">
      <div className="mb-16 grid grid-cols-12 gap-x-10">
        <div className="col-span-12 lg:col-span-3">
          <div className="eyebrow">02 / What you can ask</div>
        </div>
        <div className="col-span-12 lg:col-span-9">
          <h2 className="h-section">
            Real questions. Real answers. Real <em>citations</em>.
          </h2>
          <p className="text-ink2 mt-6 max-w-[640px] text-[18px]">
            Three exchanges from a real customer environment. Names changed, repo names kept.
          </p>
        </div>
      </div>

      <article className="mb-12 grid grid-cols-12 gap-x-10 md:mb-16">
        <div className="caption col-span-12 pt-2 md:col-span-1">a.</div>
        <div
          className="bg-surface hairline col-span-12 rounded-[8px] border p-7 md:col-span-9 md:p-9"
          style={{ boxShadow: "0 1px 0 rgb(20 17 13 / 0.02)" }}
        >
          <div className="caption mb-3">People · staffing</div>
          <p className="mono mb-5 text-[15px]">› What is Aanya working on?</p>
          <div className="rule-x mb-5" />
          <p className="text-[16.5px] leading-relaxed">
            She's the primary author on <a className="cite">#1247 · oauth-pkce</a> (merged Tuesday)
            and is deep in <a className="cite">#1259 · stripe-webhook-retries</a>, with 14 commits
            since Monday but no review request yet.
          </p>
          <p className="text-ink2 mt-3 text-[16.5px] leading-relaxed">
            Her branch <span className="mono text-[13.5px]">aanya/feat-usage-meter</span> looks
            stuck &mdash; last push 9 days ago, no PR. She also reviewed three of Marcus's PRs
            while he was on PTO.
          </p>
        </div>
      </article>

      <article className="mb-12 grid grid-cols-12 gap-x-10 md:mb-16">
        <div className="caption col-span-12 pt-2 md:col-span-1 md:col-start-3">b.</div>
        <div
          className="bg-surface hairline col-span-12 rounded-[8px] border p-7 md:col-span-9 md:col-start-4 md:p-9"
          style={{ boxShadow: "0 1px 0 rgb(20 17 13 / 0.02)" }}
        >
          <div className="caption mb-3">Throughput · diagnosis</div>
          <p className="mono mb-5 text-[15px]">› Why is the billing repo slow?</p>
          <div className="rule-x mb-5" />
          <p className="text-[16.5px] leading-relaxed">
            Two named reviewers carry 84% of <span className="mono text-[13.5px]">billing-svc</span>{" "}
            reviews (Marcus and Priya). Priya is on call this week, Marcus is on PTO &mdash; so
            review latency on that repo jumped from 6h to 38h.
          </p>
          <p className="text-ink2 mt-3 text-[16.5px] leading-relaxed">
            Three PRs are blocked on review: <a className="cite">#812</a>{" "}
            <a className="cite">#814</a> <a className="cite">#819</a>. I can suggest a temporary
            CODEOWNERS reshuffle if you want.
          </p>
        </div>
      </article>

      <article className="grid grid-cols-12 gap-x-10">
        <div className="caption col-span-12 pt-2 md:col-span-1 md:col-start-2">c.</div>
        <div
          className="bg-surface hairline col-span-12 overflow-hidden rounded-[8px] border md:col-span-10 md:col-start-3"
          style={{ boxShadow: "0 1px 0 rgb(20 17 13 / 0.02)" }}
        >
          <div className="p-7 pb-5 md:p-9">
            <div className="caption mb-3">Code · across-repo audit</div>
            <p className="mono mb-5 text-[15px]">
              › Find every place we still call{" "}
              <span style={{ color: "var(--accent)" }}>stripe.charge()</span> &mdash; are they
              still active?
            </p>
            <div className="rule-x mb-5" />
            <p className="text-[16.5px] leading-relaxed">
              Five call sites remain. Three are reachable from production code paths; two are
              inside tests or feature-flagged branches that haven't shipped in 6+ months.
            </p>
          </div>

          <div className="codeblock mx-7 mb-7 p-5 md:mx-9 md:mb-9">
            <div className="mb-3 flex items-center justify-between opacity-60">
              <span>git grep -n "stripe.charge(" $(git rev-parse HEAD)</span>
              <span>5 results · 4 files</span>
            </div>
            <div className="space-y-1.5">
              <div>
                <span style={{ color: "#7AAE6A" }}>apps/billing/src/legacy/checkout.ts</span>
                <span style={{ opacity: 0.5 }}>:142</span> &nbsp;
                <span style={{ opacity: 0.85 }}>
                  await stripe.charge({"{ amount, source }"}) // ACTIVE — fallback path, hit ~30/day
                </span>
              </div>
              <div>
                <span style={{ color: "#7AAE6A" }}>apps/billing/src/legacy/checkout.ts</span>
                <span style={{ opacity: 0.5 }}>:217</span> &nbsp;
                <span style={{ opacity: 0.85 }}>
                  stripe.charge({"{ amount, source: token }"})   // ACTIVE — admin refund flow
                </span>
              </div>
              <div>
                <span style={{ color: "#7AAE6A" }}>apps/api/src/jobs/retry-charge.ts</span>
                <span style={{ opacity: 0.5 }}>:58</span>  &nbsp;
                <span style={{ opacity: 0.85 }}>
                  return stripe.charge({"{ amount, source: src }"}) // ACTIVE — retry queue
                </span>
              </div>
              <div>
                <span style={{ color: "#E5B341" }}>apps/billing/test/legacy.spec.ts</span>
                <span style={{ opacity: 0.5 }}>:33</span>   &nbsp;
                <span style={{ opacity: 0.65 }}>
                  stripe.charge({"{ amount: 100, source: 'tok' }"}) // test fixture
                </span>
              </div>
              <div>
                <span style={{ color: "#E5B341" }}>apps/api/src/experimental/dunning.ts</span>
                <span style={{ opacity: 0.5 }}>:91</span> &nbsp;
                <span style={{ opacity: 0.65 }}>
                  if (FLAG_DUNNING_V2_OFF) stripe.charge(…) // dead since 2024-11
                </span>
              </div>
            </div>
          </div>
        </div>
      </article>
    </section>
  );
}
