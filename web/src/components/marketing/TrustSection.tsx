export function TrustSection() {
  return (
    <section
      id="methodology"
      className="container-x reveal hairline border-t py-28 md:py-36"
    >
      <div className="mb-14 grid grid-cols-12 gap-x-10">
        <div className="col-span-12 lg:col-span-4">
          <div className="eyebrow mb-4">04 / Built for engineers, not against them</div>
        </div>
        <div className="col-span-12 lg:col-span-8">
          <h2 className="h-section">
            We measure pushed work. We tell engineers what we see. We never use{" "}
            <em>"lines of code."</em>
          </h2>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-x-10 gap-y-12">
        <div className="col-span-12 lg:col-span-4 lg:col-start-5">
          <div className="caption mb-3">Scoring</div>
          <p className="text-[17px] leading-relaxed">
            Four signals: Impact, Quality, Collaboration, Consistency. Derived from review depth,
            revert rate, ownership of PRs that ship, and the work load engineers carry for one
            another. Never LOC. Never commit count.{/* . <a href="#" className="ulink text-accent ml-1">
               Read the methodology &rarr;
             </a> */}
          </p>
        </div>
        <div className="col-span-12 lg:col-span-4">
          <div className="caption mb-3">Data access</div>
          <p className="text-[17px] leading-relaxed">
            Read-only GitHub App. Per-repo allowlist. Every agent action is in an audit log you can
            export. You delete your data with one click and we mean it &mdash; the deletion job
            runs within an hour. SOC 2 Type II in progress; report on request.
          </p>
        </div>
        <div className="col-span-12 lg:col-span-4 lg:col-start-5">
          <div className="caption mb-3">Engineer self-view</div>
          <p className="text-[17px] leading-relaxed">
            Every engineer can see exactly what DyPol sees about them. Same metrics, same
            trends, same prose. There is no "manager-only" view of a person. If a tool is going to
            look at someone's work, that person should be able to look back.
          </p>
        </div>
      </div>
    </section>
  );
}
