import { PlayIcon } from "./icons";

export function VideoSection() {
  return (
    <section id="video" className="container-x reveal pt-10 pb-28 md:pb-36">
      <div className="mb-10 grid grid-cols-12 gap-x-10">
        <div className="col-span-12 lg:col-span-3">
          <div className="eyebrow">Watch it work</div>
        </div>
        <div className="col-span-12 lg:col-span-8 lg:col-start-4">
          <p
            className="text-ink display text-[22px] leading-[1.32] md:text-[26px]"
            style={{ letterSpacing: "-0.01em" }}
          >
            A 90-second tour of asking DyPol about a real engineering org &mdash;{" "}
            <span className="italic" style={{ color: "var(--ink2)" }}>
              questions, citations, and the agent's working trace.
            </span>
          </p>
        </div>
      </div>

      <div className="mx-auto" style={{ maxWidth: 1100 }}>
        <div className="video-placeholder group">
          <div className="absolute inset-0 grid place-items-center">
            <button className="play-btn" aria-label="Play tour">
              <PlayIcon />
            </button>
          </div>
          <div className="text-ink2 mono absolute top-4 left-4 text-[11px] tracking-wider uppercase">
            DyPol / Tour
          </div>
          <div className="text-ink2 mono tabular absolute top-4 right-4 text-[11px] tracking-wider uppercase">
            01:32
          </div>
          <div className="text-ink2 mono absolute bottom-4 left-4 text-[11px] tracking-wider uppercase">
            React + TypeScript repo · 14 contributors
          </div>
        </div>
        <div className="caption mt-4 text-center">DYPOL / TOUR / 1:32</div>
      </div>
    </section>
  );
}
