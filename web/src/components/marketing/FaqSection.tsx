interface Faq {
  q: string;
  a: React.ReactNode;
  border: "top" | "top-bottom";
}

const FAQS: ReadonlyArray<Faq> = [
  {
    q: "Will my engineers see this as surveillance?",
    a: (
      <>
        They will if you treat it that way. The product is built so engineers see exactly what you
        see &mdash; same metrics, same prose, same audit log. We've shipped it that way on purpose.
        Used as a 1:1 prep tool, it builds trust. Used as a leaderboard, it won't.
      </>
    ),
    border: "top",
  },
  {
    q: "What data leaves our environment?",
    a: (
      <>
        GitHub metadata and source needed to answer your questions. We never sell, share, or use
        your code to train foundation models. Embeddings stay in your tenant. On Growth and
        Enterprise plans, you can pin all inference to a region of your choice.
      </>
    ),
    border: "top",
  },
  {
    q: "How is the score calculated?",
    a: (
      <>
        Impact, Quality, Collaboration, Consistency &mdash; each on a 0–100 scale, derived from
        shipped work. The full formula is published, versioned, and runnable on your data. No
        opaque magic.{/* . <a href="#" className="ulink text-accent">
           Read the methodology &rarr;
         </a> */}
      </>
    ),
    border: "top",
  },
  {
    q: "Can I self-host?",
    a: (
      <>
        On Enterprise, yes &mdash; in a VPC of your choice on AWS or GCP. The agent and its tools
        run inside your perimeter; only billing telemetry leaves.
      </>
    ),
    border: "top",
  },
  {
    q: "What if I want my data deleted?",
    a: (
      <>
        One click in Settings. The deletion job runs within an hour and we send you a signed
        receipt with the row counts removed. Backups roll over within 30 days.
      </>
    ),
    border: "top-bottom",
  },
];

export function FaqSection() {
  return (
    <section className="container-x reveal hairline border-t py-28 md:py-36">
      <div className="mb-14 grid grid-cols-12 gap-x-10">
        <div className="col-span-12 lg:col-span-3">
          <div className="eyebrow">06 / Questions worth asking</div>
        </div>
        <div className="col-span-12 lg:col-span-9">
          <h2 className="h-section">
            Answers we'd want before <em>installing this on our own repo.</em>
          </h2>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-x-10">
        <div className="col-span-12 lg:col-span-10 lg:col-start-2">
          <dl>
            {FAQS.map((faq) => (
              <div
                key={faq.q}
                className={`hairline grid grid-cols-12 gap-x-8 border-t py-7 ${
                  faq.border === "top-bottom" ? "border-b" : ""
                }`}
              >
                <dt className="faq-q col-span-12 md:col-span-5">{faq.q}</dt>
                <dd className="text-ink2 col-span-12 mt-3 text-[16.5px] leading-relaxed md:col-span-7 md:mt-1">
                  {faq.a}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </section>
  );
}
