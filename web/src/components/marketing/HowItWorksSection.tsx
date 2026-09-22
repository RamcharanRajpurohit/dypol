const TOOLS = [
  { name: "run_sql", desc: "Read-only SQL across all your engineering metadata.", num: "01" },
  { name: "shell_exec", desc: "Any git command on read-only clones of your repos.", num: "02" },
  { name: "read_file", desc: "Inspect any file at any commit.", num: "03" },
  { name: "python_exec", desc: "Custom analysis in a sandboxed Python environment.", num: "04" },
  { name: "make_chart", desc: "Render charts inline with answers.", num: "05" },
  {
    name: "describe_schema",
    desc: "So the agent can author queries it didn't pre-know.",
    num: "06",
  },
  {
    name: "semantic_search",
    desc: "Find PRs, issues, and comments by topic, not just keyword.",
    num: "07",
  },
  { name: "summarize", desc: "Compress long context before reasoning over it.", num: "08" },
] as const;

export function HowItWorksSection() {
  return (
    <section className="container-x reveal hairline border-t py-20 md:py-36">
      <div className="mb-14 grid grid-cols-12 gap-x-10">
        <div className="col-span-12 lg:col-span-3">
          <div className="eyebrow">03 / How the agent works</div>
        </div>
        <div className="col-span-12 lg:col-span-9">
          <h2 className="h-section">
            Eight tools. <em>Any question.</em>
          </h2>
          <p className="text-ink2 mt-6 max-w-[680px] text-[17px] sm:text-[18px]">
            DyPol's agent has access to a focused set of primitives &mdash; SQL on engineering
            metadata, full git command access on read-only repo clones, file reading at any commit,
            Python for analysis, chart rendering, and semantic search across PRs and issues. It
            composes these to answer whatever you ask.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-x-10">
        <div className="col-span-12 lg:col-span-10 lg:col-start-2">
          {TOOLS.map((tool) => (
            <div key={tool.name} className="prim">
              <span className="name">{tool.name}</span>
              <span className="text-ink text-[16px]">{tool.desc}</span>
              <span className="num">{tool.num}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
