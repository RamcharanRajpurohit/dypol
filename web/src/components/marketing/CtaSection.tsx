/* import { GitHubIcon } from "./icons"; */

export function CtaSection() {
  return (
    <section id="cta" className="container-x reveal hairline border-t py-20 md:py-40">
      <div className="mx-auto max-w-[820px] text-center">
        <p
          className="display mb-10 text-[30px] leading-[1.05] sm:text-[40px] md:text-[56px]"
          style={{ letterSpacing: "-0.015em" }}
        >
          Install on GitHub.
          <br />
          See the dashboard in <em>under ten minutes</em>.
        </p>
        {/* <a href="#" className="btn-primary">
          <GitHubIcon />
          Install on GitHub
        </a> */}
      </div>
    </section>
  );
}
