export function AudienceSection() {
  return (
    <section className="container-x reveal hairline border-t py-20 md:py-36">
      <div className="mb-12 grid grid-cols-12 gap-x-10">
        <div className="col-span-12 lg:col-span-3">
          <div className="eyebrow">For</div>
        </div>
        <div className="col-span-12 lg:col-span-9">
          <h2 className="h-section">
            Two kinds of reader. <em>One question.</em>
          </h2>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-x-10 gap-y-14">
        <div className="col-span-12 lg:col-span-6">
          <div
            className="bg-surface hairline h-full rounded-[10px] border p-6 sm:p-9"
            style={{ boxShadow: "0 1px 0 rgb(20 17 13 / 0.02)" }}
          >
            <div className="caption mb-4">Founders & CTOs</div>
            <h3
              className="display mb-5 text-[26px] leading-[1.1] sm:text-[34px]"
              style={{ letterSpacing: "-0.01em" }}
            >
              You stopped reading the dashboard six weeks ago.
            </h3>
            <p className="text-ink2 mb-8 text-[16.5px] leading-relaxed">
              DyPol replaces the ritual of "checking the metrics" with a one-line question. Ask once
              a week. Get a paragraph back. Forward it to the board.
            </p>
            <figure className="hairline border-t pt-6">
              <blockquote className="italic-serif text-ink mb-3 text-[20px] leading-[1.35]">
                "{`{quote from design partner}`}"
              </blockquote>
              <figcaption className="caption">Founder · 22-person Series A</figcaption>
            </figure>
          </div>
        </div>

        <div className="col-span-12 lg:col-span-6 lg:pt-10">
          <div className="hairline border-t border-b px-1 py-6 sm:py-9">
            <div className="caption mb-4" style={{ color: "var(--accent)" }}>
              VPs of Engineering
            </div>
            <h3
              className="display mb-5 text-[26px] leading-[1.1] sm:text-[34px]"
              style={{ letterSpacing: "-0.01em" }}
            >
              One-on-ones, with the data already loaded.
            </h3>
            <p className="text-ink2 mb-8 text-[16.5px] leading-relaxed">
              Walk into reviews knowing what each engineer shipped, who they helped, and where they
              got stuck. Not as a scorecard &mdash; as a way to ask better questions.
            </p>
            <figure>
              <blockquote className="italic-serif text-ink mb-3 text-[20px] leading-[1.35]">
                "{`{quote from design partner}`}"
              </blockquote>
              <figcaption className="caption">VP Eng · 60-person Series B</figcaption>
            </figure>
          </div>
        </div>
      </div>
    </section>
  );
}
