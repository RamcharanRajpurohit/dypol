# DyPol — Product Requirements Document (v2)

*An AI engineering analyst for startup founders and eng leaders.*

---

## 1. Vision

DyPol is not a dashboard. It is a **data analyst for your engineering organization** — an AI agent with full read access to your GitHub metadata and source code, equipped with the same kind of capabilities a human analyst would have (SQL, Python, git, file reading, charts) plus a model smart enough to compose any answer from those primitives.

Every existing tool in this space (LinearB, Swarmia, Jellyfish, GitClear) is a fixed dashboard with fixed metrics. The founder's real questions — *"why is billing slow this sprint?"*, *"what changed in the auth flow in March?"*, *"who's actually struggling?"* — don't fit those dashboards. DyPol's interface is **ask anything**, backed by an agent that can investigate, run analysis, read the actual diffs, and answer with citations grounded in real data.

---

## 2. Problem

Founders and engineering leaders at 5–100 person companies cannot reliably answer:

- Are we shipping the right things, fast enough?
- Who's actually contributing value vs who's just busy?
- Which repo or initiative is silently stuck, and why?
- What changed in the codebase last month that we should know about?
- Who needs help right now?

Today they get this through manual GitHub scrolling (doesn't scale past 5 devs), 1:1 meetings (subjective, slow), or enterprise tools that cost $30+/dev/month, take weeks to set up, and only show pre-defined metrics.

**The gap**: nothing exists for the 10–50 dev range that's affordable, sets up in 5 minutes, and answers the actual questions people have rather than the questions someone designed a dashboard around.

---

## 3. Target users

**Persona A — Startup founder** (technical or product, 10–30 person company, no dedicated EM)
- Wants: a Monday-morning answer to "is engineering on track?"
- Pain: doesn't have time to read every PR; doesn't trust gut feel; can't ask managers without it being political
- Won't tolerate: complex setup, jargon, dashboards with 40 metrics, vanity scores

**Persona B — VP Engineering / Head of Eng** (20–100 person company)
- Wants: drill into specific devs, repos, and trends; identify blockers fast
- Pain: too many 1:1s; can't be everywhere; performance reviews are vibes
- Won't tolerate: anything that looks like surveillance, or "lines of code" metrics — that destroys engineer trust

**Persona C — Tech lead** (secondary, team of 5–10)
- Wants: tactical "what's blocking my team this week"

---

## 4. Goals (v1)

1. **5-minute setup**: install GitHub App, repos cloned and indexed, first dashboard live within 10 minutes
2. **Two answer modes**: cached/instant for common questions, agent-driven for novel ones
3. **Defensible scoring** — every score has a "why" breakdown engineers won't dispute
4. **Honest signals** — surface what's stuck, who needs help, never invent insights from data we don't have
5. **Plain English output** that a non-technical founder can act on

---

## 5. Non-goals (v1)

- Public repo browsing / showcase mode
- Code quality / lint / static analysis (we read code, we don't grade it)
- Mobile native app
- Jira / Linear / Asana integration (v2)
- Custom scoring weight tuning UI (v2)
- Performance review automation — explicitly out of scope, ethically and legally
- Source code modification or PR creation — read-only, always

---

## 6. User stories

- As a founder, I open the dashboard Monday and know in 30 seconds what shipped, what's stuck, and who needs help.
- As a founder, I get a weekly email digest in plain English, no jargon.
- As a VP Eng, I click any dev and see a 4-dimension score breakdown plus an LLM-generated 2-line characterization grounded in their actual PRs.
- As a VP Eng, I ask *"why is the billing repo behind?"* and get an answer that references specific PRs, reviewer workloads, and the actual stuck files — not generic dashboard metrics.
- As a tech lead, I ask *"find every place we still use the old auth helper"* and the agent greps the codebase and lists call sites with file paths and line numbers.
- As a founder, I ask *"how has cycle time changed across our repos in the last 90 days, normalized for PR size?"* and get a chart plus 3 paragraphs of analysis, generated on demand.
- As an admin, I install the GitHub App on my org, select repos, and configure who has access.

---

## 7. Architecture: three tiers

The system serves answers from three layers, each progressively more powerful and more expensive. Sonnet 4.6 routes between them based on the question.

### Tier 1 — Cached (instant, free at read time)

Pre-computed outputs refreshed on a schedule:

- Weekly repo digests (Monday 6am)
- Dev contribution scores (recomputed hourly)
- Dev characterizations (the 2-liner LLM blurb — recomputed weekly)
- Repo health classifications (Healthy/Hot/Stuck/Maintenance/Abandoned — every 6 hours)
- Org-wide weekly digest

These power the dashboard's default views. Most user interactions hit this layer and never invoke the agent.

### Tier 2 — Scoped tools (fast, ~$0.01/query, ~3s)

For common Q&A patterns, named tools backed by SQL + cached LLM outputs:

- `get_dev_activity(name, days)` — full picture of one person
- `get_repo_summary(name, days)` — repo status with cached digest
- `list_alerts(category)` — current stuck-work alerts
- `compare_periods(metric, scope, period_a, period_b)` — trend comparisons
- `get_pr_details(number, repo)` — drill into a single PR
- `list_devs(filters, sort)` — enumerate with filters

The agent calls these when a question fits, then synthesizes a final answer. Cheap, fast, predictable.

### Tier 3 — Code-executing agent (novel questions, ~$0.15/query, ~20s)

When a question doesn't fit a named tool — or requires actual investigation — the agent gets dropped into a sandbox with **primitives** and figures out the answer itself.

Triggered by the "Ask Anything" / "Deep Analysis" surface, or when Tier 2 tools don't cover the question.

---

## 8. The agent's primitives

The Tier 3 agent has the same kind of capabilities a human analyst (or the assistant you're talking to right now) would have:

| Primitive | What it does | Example use |
|---|---|---|
| `run_sql(query)` | Read-only SQL on the customer's metadata DB (Postgres) | Compute custom metrics across PRs/reviews/devs |
| `shell_exec(command, repo, ref)` | **Run any shell command (incl. all git commands) inside an ephemeral sandbox with a read-only clone of the specified repo at the specified ref** | `git log --since=2026-01-01 -- src/billing/`, `git blame src/auth.py`, `git diff main..feature/billing-v2`, `rg "stripe.charge" --type=py` |
| `read_file(repo, path, ref)` | Read any file at any commit | Inspect actual code, see what changed, decode logic |
| `python_exec(code)` | Run Python in the sandbox (pandas, numpy, plotly, sqlalchemy, customer's data already mounted) | Custom analysis, transformations, charting |
| `make_chart(data, spec)` | Render a chart and attach to the response | Visualize trends, comparisons, distributions |
| `describe_schema()` | Return all DB tables, columns, types, relationships | Lets the agent author queries without prior knowledge |
| `semantic_search(query, scope)` | pgvector search over PRs, issues, review comments, commit messages | "Find work related to billing performance" |
| `summarize(text, instructions)` | Recursive Claude call for compressing long content | Summarize 200 commits before reasoning over them |

**Critical capability — full git access.** The agent can run any read-only git command against a clone of any repo it has been granted access to. This is what lets it answer questions like *"what did Aanya change in the auth module last week"* or *"why does this PR keep failing — show me the failing test and the recent changes to that file."* Without git access, the agent is limited to metadata; with it, the agent can inspect the actual code, exactly the way an engineer would.

---

## 9. Repo storage and sync

To support code-level analysis, DyPol maintains read-only clones of customer repos.

**Storage**:
- Per-org bare clones in encrypted block storage
- Typical 50-dev org: ~100 repos × avg 200MB = ~20GB per org
- Estimated infra cost at scale (50 orgs): ~$50/month in storage

**Sync**:
- Initial: shallow clone on org install (last 90 days of history); deepen lazily on demand
- Ongoing: webhook-driven `git fetch` on `push`, `pull_request`, and `create` events
- Latency target: <10s from GitHub event to clone updated

**Sandbox provisioning**:
- Pool of pre-warmed E2B (or Modal) sandboxes
- On query: mount relevant repo clone(s) read-only into a fresh sandbox
- Sandbox lifetime: single query (destroyed after answer)
- Cold start: <2s; warm pool keeps p50 mount time <500ms

**Retention**:
- Clones retained while customer subscription is active
- Customer can request deletion of any repo from DyPol (sync stops, clone wiped within 24h)
- Account deletion: all clones, metadata, embeddings purged within 7 days

---

## 10. Security and privacy

This is non-negotiable. DyPol stores customer source code, so the bar is enterprise-grade from day one.

**GitHub access**
- Installed as a GitHub App with **read-only** scopes (`contents: read`, `metadata: read`, `pull_requests: read`, `issues: read`, `members: read`). Never request write access.
- Per-installation tokens, never store user OAuth tokens long-term.

**Data isolation**
- Multi-tenant Postgres with **row-level security** policies — every query scoped to the requesting org's `org_id`. Even a buggy query cannot cross tenants.
- Repo clones in per-org encrypted volumes with separate encryption keys (envelope encryption via cloud KMS).
- Sandbox containers isolated per query; no persistent state between queries; no network egress except to whitelisted services (Anthropic API, internal control plane).

**LLM data handling**
- Only **excerpts** the agent fetches per query reach the LLM. Never wholesale code dumps.
- All LLM calls go to Anthropic with zero data retention enabled.
- No customer data used to train models — Anthropic API guarantees this.

**Operational**
- Audit log of every agent action (tool calls, files read, commands run) per org, retained 90 days, customer-accessible.
- Encryption at rest (AES-256) and in transit (TLS 1.3) on every channel.
- SOC 2 Type I readiness target: month 4 post-launch. Type II: year 1.
- Public security & privacy page from day one. Customers will check.

**User-facing transparency**
- Methodology page explaining what we measure, what we don't (local work, pair programming, DMs), and how scores are computed.
- Per-dev "view my own data" page so engineers see exactly what the system sees about them. This earns trust and prevents revolts.

---

## 11. Feature spec (v1)

### 11.1 Onboarding
- Sign in with GitHub
- Install GitHub App on org (one click; org admin permissions)
- Select which repos to track (default: all)
- Backfill last 90 days of metadata + shallow clone (<10 min for typical org)
- Optional: connect Slack workspace for digest delivery

### 11.2 Org overview (home dashboard)
- Headline KPIs: PRs merged this week, cycle time, active devs, repos shipped to
- 12-week sparkline trends per KPI
- "Needs attention" panel (3–5 highest priority alerts)
- Top/bottom 5 score movers this week

### 11.3 Dev leaderboard + profiles
- Sortable table: name, role, score, weekly trend
- Click any dev → profile page with:
  - 4-dimension score breakdown (Impact, Quality, Collaboration, Consistency) with formula explanation
  - LLM-generated 2-line characterization, refreshed weekly
  - Recent merged PRs with AI summaries
  - Active branches without PRs (the "ghost work" view)
  - Reviews given/received
  - Workload signal (open PRs assigned, PRs awaiting their review)

### 11.4 Repo health board
- Each repo classified: Healthy / Hot / Stuck / Maintenance / Abandoned
- Repo detail page:
  - Activity trend (12 weeks)
  - Open PR queue with age coloring
  - Top contributors this period
  - LLM weekly summary

### 11.5 Weekly digest
- Generated Monday 6am org time
- In-app + email + (optional) Slack
- Plain English, founder-readable, citing PR numbers

### 11.6 Stuck-work detector
- PRs unreviewed >7 days
- PRs with >3 review cycles
- Repos with falling commit cadence + rising open issues
- Devs with review starvation (own PRs unreviewed >5 days)
- Surfaced on dashboard + included in digest

### 11.7 Ask Anything (Tier 3 agent)
- Natural language input box
- Streamed response with live tool-call indicators ("Reading billing repo…", "Running analysis…")
- Citations on every claim (PR/issue numbers, file paths with line numbers)
- Charts rendered inline when generated
- Conversation history per user (so follow-ups have context)
- Cap: 5 deep analyses per org per day on the startup tier; unlimited on growth

### 11.8 Settings
- Repo selection
- Team invites + roles (admin / member / viewer)
- Digest schedule + delivery channels
- BYOK (optional Anthropic API key for higher Tier 3 limits)
- Repo deletion / data export

---

## 12. Non-functional requirements

**Performance**
- Dashboard load: <1.5s (cached aggregates)
- Tier 2 query: <5s p95
- Tier 3 query: <30s p95, <60s p99
- Sync lag: <10s from GitHub event to dashboard

**Scale targets (v1)**
- 50 paying orgs
- Avg org: 15 devs, 25 repos, ~10K PRs/month
- ~500K total PRs/month flowing through the pipeline
- ~200 Tier 3 queries/day org-wide

**Reliability**
- 99.5% uptime target for v1 (one 9 above hobby)
- Graceful degradation: if Tier 3 sandbox is down, fall back to Tier 2 with explanation
- Webhook delivery is at-least-once; idempotent processing required

---

## 13. Tech stack

**Frontend**
- Next.js 14+ App Router, TypeScript
- Tailwind + shadcn/ui (production components free)
- Recharts or Tremor for visualizations
- TanStack Query for client state
- Auth: Clerk (fastest to ship)

**Backend**
- Python 3.12 + FastAPI
- PostgreSQL 15+ with `pgvector` extension
- Redis (cache, rate limit, Celery broker)
- Celery + Celery Beat for background jobs
- GitHub App via `gidgethub` (async)
- Webhook receiver as separate FastAPI route group with HMAC signature verification

**Agent and sandbox layer**
- Anthropic SDK (Python) with tool use
- Claude Sonnet 4.6 for the orchestrator and Tier 3 agent
- Claude Haiku 4.5 for bulk classification (review comment substantive-ness, PR labeling)
- Voyage AI for embeddings (or OpenAI `text-embedding-3-small`)
- **E2B sandboxes** for the Tier 3 code execution layer (managed, fastest to ship; alternative: Modal or self-hosted Firecracker)
- Pre-installed in sandbox: `pandas`, `numpy`, `plotly`, `sqlalchemy`, `gitpython`, `ripgrep`, plus a `dypol` helper Python package

**LLM cost optimization**
- Anthropic prompt caching on system prompt + tool definitions (cuts repeated tokens ~90%)
- Tool result caching keyed by `(org_id, tool, args_hash)`, TTL 1h
- Semantic query cache via pgvector (similar questions → cached answer)
- Tier-based budget caps per org per day

**Infra**
- Frontend: Vercel
- Backend + DB + Redis + workers: Railway or Render (v1) → AWS later
- Object storage for repo clones: AWS S3 with SSE-KMS (or R2 for cheaper egress)
- Sandbox: E2B managed
- CI/CD: GitHub Actions
- Errors: Sentry
- Tracing: Langfuse (open-source LLM observability)
- Product analytics: PostHog
- Email: Resend
- Status page: BetterStack

**Total monthly infra cost at v1 scale (~20 design partners)**: ~$150–250/month including LLM costs at expected query volume.

---

## 14. Architecture diagram

```
                           GitHub
                              │
              ┌───────────────┴───────────────┐
              │ Webhooks                       │ Git fetch
              ▼                                ▼
      FastAPI receiver               Clone sync worker
       (sig verified)                (writes to S3+KMS)
              │
              ▼
        Celery queue
              │
       ┌──────┴──────┬──────────────┬──────────┐
       ▼             ▼              ▼          ▼
   Metrics       Scoring       Embedding   Cached LLM
   updater       engine        indexer     outputs
       │             │              │          │
       └─────────────┴──────────────┴──────────┘
                         │
                         ▼
                    PostgreSQL
                  (pgvector + RLS)
                         │
                         ▼
              ┌───────── FastAPI read API ─────────┐
              │                                     │
              ▼                                     ▼
       Next.js dashboard                   Agent orchestrator
       (Tier 1 cached)                     (Tier 2 + Tier 3)
                                                   │
                                                   ▼
                                          Claude Sonnet 4.6
                                          + tool use loop
                                                   │
                                                   ▼
                                          E2B sandbox per query
                                          - read-only repo clone
                                          - run_sql, shell_exec,
                                            python_exec, etc.
```

---

## 15. Timeline (10 weeks, full-time solo; 18–20 weeks part-time)

| Week | Deliverable |
|---|---|
| 1 | Project skeleton, Clerk auth, GitHub App registration, OAuth/install flow |
| 2 | Webhook receiver + repo clone sync worker + Postgres schema with RLS |
| 3 | Scoring engine v1 + dev profile page + leaderboard |
| 4 | Repo health classifier + repo detail page |
| 5 | Org overview dashboard + stuck-work alerts |
| 6 | LLM layer — dev characterizations, repo summaries (cached) |
| 7 | Weekly digest (in-app + email + Slack) |
| 8 | **Tier 2 agent**: scoped tools + orchestrator with prompt caching |
| 9 | **Tier 3 agent**: E2B sandbox integration + primitives (`run_sql`, `shell_exec`, `python_exec`, `read_file`, `make_chart`) + Ask Anything UI |
| 10 | Eval harness, observability (Langfuse), security/privacy page, landing page, demo, deploy |

Tier 3 is the new ~3 weeks of work vs the previous plan; the rest tracks the earlier timeline.

---

## 16. Eval harness (mandatory, not optional)

Agentic systems regress silently. Build the eval set from week 8.

```
EVALS = [
  {
    "question": "What is Aanya working on?",
    "expected_tier": 2,
    "must_call": ["get_dev_activity"],
    "must_cite_pr_numbers": True,
    "max_tool_calls": 2
  },
  {
    "question": "Why is the billing repo behind?",
    "expected_tier": 2,  # may escalate to 3
    "must_call_one_of": ["get_repo_summary", "get_pr_details"],
    "must_cite_pr_numbers": True,
    "max_tool_calls": 5
  },
  {
    "question": "How has review latency changed across repos in 90d, normalized for PR size?",
    "expected_tier": 3,
    "must_call_one_of": ["run_sql", "python_exec"],
    "must_produce_chart": True,
    "max_tool_calls": 10
  },
  {
    "question": "Find every call site of stripe.charge() and tell me which are still active",
    "expected_tier": 3,
    "must_call": ["shell_exec"],   # ripgrep across the repo
    "must_cite_file_paths": True,
    "max_tool_calls": 8
  },
  # 30–50 of these covering common patterns + edge cases
]
```

Run nightly. Track tool selection accuracy, citation rate, latency, cost, ground-truth match (LLM-as-judge against hand-written gold answers). Block deploys that regress on the eval set by >5%.

---

## 17. Pricing (target — not built v1)

| Tier | Price | Limits |
|---|---|---|
| Free | $0 | Up to 5 devs, 1 repo, no Tier 3 agent |
| Startup | $15/dev/mo | Unlimited repos, 5 Tier 3 queries/day, weekly digest, Slack |
| Growth | $25/dev/mo | Unlimited Tier 3, custom scoring weights, SSO, audit log access |
| Enterprise | Contact | Self-hosted option, custom SLA, dedicated support |

LinearB and Swarmia start at $30+/dev/mo. Undercut hard, justify with simplicity + agentic depth.

---

## 18. Success metrics (v1, by week 16)

- **5–10 design partner orgs** actively using DyPol weekly
- **Weekly digest open rate >40%**
- **Tier 3 queries per active user >3/week** (meaningful engagement, not just dashboard views)
- **Engineer trust signal**: <10% of engineers in design partner orgs request opt-out of scoring
- **Eval pass rate >85%** on the curated set, stable across 4 consecutive weeks

---

## 19. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Engineers feel surveilled | Transparent score breakdown; no LOC/commit-count metrics; per-dev self-view; explicit methodology page |
| Tier 3 agent hallucinates | Strict grounding requirement in system prompt; citation enforcement in eval; LLM-as-judge checks for unsupported claims |
| Sandbox security breach | Defense in depth: read-only mounts, no network egress, ephemeral containers, per-org KMS keys, audit log |
| LLM cost runs away | Per-query budget cap (max 6 tools, max $0.50); per-org daily ceiling; circuit breaker on anomalies |
| Repo clone storage explodes | Shallow clones by default; deepen on demand; retention policies; tiered storage (recent in SSD, cold in glacial) |
| GitHub rate limits | GitHub App quotas scale per-installation; webhook-driven sync minimizes polling; backoff + retry on workers |
| Founder doesn't open digest | Mobile-optimized email; 5-bullet format; A/B test subject lines; track open rates and iterate |
| Tier 3 too slow / too expensive | Aggressive prompt caching; semantic query cache; pre-warmed sandbox pool; fall back to Tier 2 with note when budget exceeded |
| Source code storage spooks customers | Clear privacy page; SOC 2 readiness early; self-hosted option on enterprise tier; explicit deletion guarantees |

---

## 20. Open questions for v1 design

These need decisions before development starts:

1. **Sandbox provider**: E2B (managed, fast) vs Modal (more control) vs self-hosted Firecracker (most control, slowest to build). Recommendation: E2B for v1.
2. **Auth**: Clerk vs Auth.js. Recommendation: Clerk for v1 ship speed; revisit at series A.
3. **Storage region for clones**: single region (US) for v1, multi-region for enterprise tier later?
4. **Design partner sourcing**: how many to target, from where (HN, IndieHackers, Twitter), what does the pilot agreement look like?
5. **Naming**: lock the product name and domain in week 1.

---

## 21. What makes this defensible

Three moats compound over time:

1. **The agentic UX** — competitors are dashboard-first; switching to agent-first is a cultural and architectural rebuild for them.
2. **The eval set + tuning** — the longer DyPol runs, the better its eval set (real production queries become eval cases), and the better its agent gets at this specific domain.
3. **The trust layer** — methodology page, per-dev self-view, transparent scoring. These take time to build and harder to replicate than features.

---

*End of PRD v2.*
