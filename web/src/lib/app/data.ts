import type {
  ActivityEvent,
  AskAnswer,
  ConversationBucket,
  Contributor,
  Dev,
  Repo,
} from "./types";

export const DEVS: ReadonlyArray<Dev> = [
  {
    rank: "01",
    name: "Aanya Sharma",
    handle: "@aanya",
    role: "Staff · Platform",
    avatar: "AS",
    color: 0,
    score: 94,
    impact: 96,
    quality: 91,
    collab: 97,
    consist: 92,
    week: "Shipped 4 / Reviewed 11",
    sparkD: "M0 12 L8 10 L16 11 L24 8 L32 7 L40 6 L48 4 L56 5",
    delta: "+3",
  },
  {
    rank: "02",
    name: "Priya Nair",
    handle: "@priya",
    role: "Senior · Billing",
    avatar: "PN",
    color: 4,
    score: 88,
    impact: 84,
    quality: 93,
    collab: 90,
    consist: 85,
    week: "Shipped 3 / Reviewed 8",
    sparkD: "M0 14 L8 12 L16 10 L24 9 L32 11 L40 8 L48 7 L56 6",
    delta: "+1",
  },
  {
    rank: "03",
    name: "Marcus Chen",
    handle: "@marcus",
    role: "Senior · Infra",
    avatar: "MC",
    color: 5,
    score: 84,
    impact: 88,
    quality: 82,
    collab: 78,
    consist: 88,
    week: "Shipped 2 / Reviewed 4",
    sparkD: "M0 8 L8 9 L16 7 L24 8 L32 7 L40 9 L48 8 L56 6",
    delta: "—",
  },
  {
    rank: "04",
    name: "Raj Patel",
    handle: "@raj",
    role: "Senior · Auth",
    avatar: "RP",
    color: 3,
    score: 81,
    impact: 79,
    quality: 85,
    collab: 80,
    consist: 80,
    week: "Shipped 3 / Reviewed 6",
    sparkD: "M0 10 L8 11 L16 9 L24 10 L32 8 L40 7 L48 9 L56 7",
    delta: "+2",
  },
  {
    rank: "05",
    name: "Sam Park",
    handle: "@sam",
    role: "Mid · Mobile",
    avatar: "SP",
    color: 7,
    score: 76,
    impact: 74,
    quality: 78,
    collab: 72,
    consist: 79,
    week: "Shipped 4 / Reviewed 5",
    sparkD: "M0 13 L8 11 L16 12 L24 9 L32 10 L40 8 L48 9 L56 8",
    delta: "+5",
  },
  {
    rank: "06",
    name: "Jordan Lee",
    handle: "@jordan",
    role: "Senior · API",
    avatar: "JL",
    color: 6,
    score: 74,
    impact: 78,
    quality: 69,
    collab: 75,
    consist: 74,
    week: "Shipped 2 / Reviewed 7",
    sparkD: "M0 11 L8 10 L16 12 L24 11 L32 9 L40 10 L48 8 L56 9",
    delta: "-1",
  },
  {
    rank: "07",
    name: "Noor Khan",
    handle: "@noor",
    role: "Senior · Data",
    avatar: "NK",
    color: 2,
    score: 72,
    impact: 76,
    quality: 74,
    collab: 68,
    consist: 70,
    week: "Shipped 1 / Reviewed 4",
    sparkD: "M0 9 L8 8 L16 10 L24 9 L32 11 L40 10 L48 11 L56 12",
    delta: "-3",
  },
  {
    rank: "08",
    name: "Diego Ortiz",
    handle: "@diego",
    role: "Mid · API",
    avatar: "DO",
    color: 1,
    score: 69,
    impact: 65,
    quality: 73,
    collab: 70,
    consist: 68,
    week: "Shipped 2 / Reviewed 3",
    sparkD: "M0 12 L8 11 L16 11 L24 10 L32 11 L40 10 L48 9 L56 10",
    delta: "+1",
  },
  {
    rank: "09",
    name: "Mia Tanaka",
    handle: "@mia",
    role: "Mid · Mobile",
    avatar: "MT",
    color: 0,
    score: 67,
    impact: 62,
    quality: 71,
    collab: 68,
    consist: 67,
    week: "Shipped 1 / Reviewed 3",
    sparkD: "M0 10 L8 11 L16 10 L24 11 L32 11 L40 12 L48 11 L56 11",
    delta: "—",
  },
  {
    rank: "10",
    name: "Eliot Brun",
    handle: "@eliot",
    role: "Junior · Web",
    avatar: "EB",
    color: 4,
    score: 62,
    impact: 58,
    quality: 64,
    collab: 65,
    consist: 60,
    week: "Shipped 1 / Reviewed 2",
    sparkD: "M0 11 L8 11 L16 12 L24 11 L32 12 L40 12 L48 13 L56 12",
    delta: "+4",
  },
];

export const REPOS: ReadonlyArray<Repo> = [
  {
    name: "billing-svc",
    status: "hot",
    openPRs: 12,
    sum: "3 stuck PRs · cycle time up 40% · 5 active",
    spark: [3, 5, 2, 4, 6, 7, 4, 8, 5, 9, 7, 4],
  },
  {
    name: "hydra-api",
    status: "hot",
    openPRs: 8,
    sum: "Test flakiness up 2.4× · 6 active",
    spark: [4, 3, 5, 4, 6, 5, 7, 6, 5, 7, 8, 5],
  },
  {
    name: "auth-svc",
    status: "ok",
    openPRs: 3,
    sum: "PKCE rollout shipped · 4 active",
    spark: [5, 7, 8, 6, 9, 7, 8, 9, 7, 8, 6, 7],
  },
  {
    name: "mobile-app",
    status: "ok",
    openPRs: 5,
    sum: "Onboarding rewrite shipped · 3 active",
    spark: [2, 3, 4, 3, 5, 4, 5, 6, 4, 5, 6, 5],
  },
  {
    name: "web-marketing",
    status: "neutral",
    openPRs: 1,
    sum: "Maintenance · 1 contributor",
    spark: [1, 0, 2, 1, 1, 0, 1, 2, 0, 1, 1, 0],
  },
  {
    name: "infra-terraform",
    status: "ok",
    openPRs: 2,
    sum: "Postgres 16 migration · 2 active",
    spark: [3, 2, 4, 3, 3, 4, 5, 3, 4, 3, 4, 3],
  },
  {
    name: "admin-tools",
    status: "ok",
    openPRs: 2,
    sum: "Refund flow shipped · 2 active",
    spark: [1, 2, 1, 2, 3, 2, 3, 2, 3, 2, 3, 4],
  },
  {
    name: "cli",
    status: "neutral",
    openPRs: 1,
    sum: "Two ergonomics improvements · 1 active",
    spark: [0, 1, 0, 1, 1, 0, 1, 0, 1, 0, 1, 1],
  },
  {
    name: "docs-site",
    status: "neutral",
    openPRs: 0,
    sum: "No activity in 8 days",
    spark: [1, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0],
  },
  {
    name: "analytics-pipe",
    status: "stuck",
    openPRs: 4,
    sum: "1 stuck branch · last merge 14 days ago",
    spark: [2, 1, 2, 1, 1, 0, 0, 0, 1, 0, 0, 0],
  },
  {
    name: "design-tokens",
    status: "ok",
    openPRs: 1,
    sum: "Quiet week · 2 active",
    spark: [1, 1, 2, 1, 1, 2, 1, 2, 2, 1, 2, 1],
  },
];

export const CONTRIBUTORS: ReadonlyArray<Contributor> = [
  {
    rank: "01",
    name: "Aanya Sharma",
    score: 94,
    color: 0,
    avatar: "AS",
    delta: "+3",
    spark: "M0 12 L8 10 L16 11 L24 8 L32 7 L40 6 L48 4 L56 5",
  },
  {
    rank: "02",
    name: "Priya Nair",
    score: 88,
    color: 4,
    avatar: "PN",
    delta: "+1",
    spark: "M0 14 L8 12 L16 10 L24 9 L32 11 L40 8 L48 7 L56 6",
  },
  {
    rank: "03",
    name: "Marcus Chen",
    score: 84,
    color: 5,
    avatar: "MC",
    delta: "—",
    spark: "M0 8 L8 9 L16 7 L24 8 L32 7 L40 9 L48 8 L56 6",
  },
  {
    rank: "04",
    name: "Raj Patel",
    score: 81,
    color: 3,
    avatar: "RP",
    delta: "+2",
    spark: "M0 10 L8 11 L16 9 L24 10 L32 8 L40 7 L48 9 L56 7",
  },
  {
    rank: "05",
    name: "Sam Park",
    score: 76,
    color: 7,
    avatar: "SP",
    delta: "+5",
    spark: "M0 13 L8 11 L16 12 L24 9 L32 10 L40 8 L48 9 L56 8",
  },
];

export const ACTIVITY: ReadonlyArray<ActivityEvent> = [
  {
    who: "Aanya Sharma",
    color: 0,
    avatar: "AS",
    what: "merged",
    detail: '#1247 oauth-pkce in <span class="mono text-[12.5px]">auth-svc</span>',
    when: "12m ago",
  },
  {
    who: "Sam Park",
    color: 7,
    avatar: "SP",
    what: "opened",
    detail: '#828 receipt PDFs · i18n in <span class="mono text-[12.5px]">billing-svc</span>',
    when: "1h ago",
  },
  {
    who: "Priya Nair",
    color: 4,
    avatar: "PN",
    what: "reviewed",
    detail: "#823 webhook signature verification",
    when: "2h ago",
  },
  {
    who: "Marcus Chen",
    color: 5,
    avatar: "MC",
    what: "pushed",
    detail:
      '4 commits to <span class="mono text-[12.5px]">marcus/spike-clickhouse-eval</span>',
    when: "4h ago",
  },
  {
    who: "Raj Patel",
    color: 3,
    avatar: "RP",
    what: "commented on",
    detail: "#812 webhook retries with idempotency keys",
    when: "yesterday",
  },
  {
    who: "Aanya Sharma",
    color: 0,
    avatar: "AS",
    what: "requested review on",
    detail: "#824 usage-meter contract types",
    when: "yesterday",
  },
  {
    who: "Noor Khan",
    color: 2,
    avatar: "NK",
    what: "pushed",
    detail: '2 commits to <span class="mono text-[12.5px]">noor/schema-migration-v2</span>',
    when: "mon",
  },
];

export const CONVERSATION_HISTORY: ReadonlyArray<ConversationBucket> = [
  {
    label: "Today",
    items: [
      { label: "What is Aanya working on?", question: "What is Aanya working on?" },
      { label: "Why is the billing repo slow?", question: "Why is the billing repo slow?" },
    ],
  },
  {
    label: "Yesterday",
    items: [
      { label: "What did we ship last week?", question: "What did we ship last week?" },
      {
        label: "stripe.charge() audit",
        question:
          "Find every place we still call stripe.charge() — are they still active?",
      },
      {
        label: "Reviewer load distribution",
        question: "Reviewer load distribution this sprint",
      },
    ],
  },
  {
    label: "Last week",
    items: [
      {
        label: "Stuck branches by author",
        question: "Who has the most stuck branches right now?",
      },
      { label: "PRs touching /auth in Q1" },
      { label: "Time-to-first-review trend" },
      { label: "Hotspot files by churn" },
    ],
  },
];

export const ASK_SUGGESTIONS: ReadonlyArray<string> = [
  "What did Aanya ship this week?",
  "Why is the billing repo behind?",
  "Show review latency by repo",
];

export const ASK_ANSWERS: Readonly<Record<string, AskAnswer>> = {
  "What is Aanya working on?": {
    tools: [
      "Reading auth-svc and billing-svc metadata…",
      "git log --author=aanya --since=7d",
      "Cross-referencing open PRs and stuck branches",
      "Composing answer with citations",
    ],
    answer: () => `
      <p>Aanya is the primary author on <a class="pill">#1247 · oauth-pkce</a> (merged Tuesday) and is currently deep in <a class="pill">#1259 · billing/stripe-webhook-retries</a> &mdash; she's pushed <span class="num">14 commits</span> since Monday but hasn't requested review yet.</p>
      <p class="muted">One branch looks stuck: <span class="filepath">aanya/feat-usage-meter</span> &mdash; last push 9 days ago, no PR opened. She's also reviewed three of Marcus's PRs while he was on PTO.</p>`,
    sources: [
      {
        kind: "PULL REQUESTS",
        items: [
          { t: "#1247 · oauth-pkce", d: "auth-svc · merged Tue" },
          { t: "#1259 · stripe-webhook-retries", d: "billing-svc · in flight" },
          { t: "#824 · usage-meter contract types", d: "billing-svc · in review" },
        ],
      },
      {
        kind: "FILES",
        items: [
          { t: "apps/auth/oauth/pkce.ts", d: "+182 / -47 last 7d" },
          { t: "apps/billing/webhooks/retries.ts", d: "+96 / -22 last 3d" },
        ],
      },
      {
        kind: "DEVS",
        items: [{ t: "Aanya Sharma", d: "@aanya · Staff · Platform" }],
      },
    ],
    followups: [
      "Summarize the diff on #1259",
      "Draft a nudge for the stuck branch",
      "Show her review load this week",
    ],
  },
  "Why is the billing repo slow?": {
    tools: [
      "Querying review_latency_p50 by repo, last 14d",
      "Pulling reviewer set for billing-svc",
      "git log --merges billing-svc --since=14d",
      "Generating chart…",
    ],
    answer: () => `
      <p>Two named reviewers carry <span class="num">84%</span> of <span class="filepath">billing-svc</span> reviews (Marcus and Priya). Priya is on call this week, Marcus is on PTO &mdash; review latency on that repo jumped from <span class="num">6h</span> to <span class="num">38h</span>.</p>
      <div class="card p-4 my-4">
        <div class="flex items-center justify-between mb-3"><span class="label-tight">Review latency · billing-svc · 14d</span><span class="mono text-[10.5px]" style="color: var(--ink3);">p50, hours</span></div>
        <div class="bars" style="height: 60px;">
          <div style="height: 18%"></div><div style="height: 22%"></div><div style="height: 16%"></div>
          <div style="height: 24%"></div><div style="height: 20%"></div><div style="height: 28%"></div>
          <div style="height: 30%"></div><div style="height: 26%"></div><div style="height: 35%"></div>
          <div style="height: 70%" class="hi"></div><div style="height: 84%" class="hi"></div>
          <div style="height: 92%" class="hi"></div><div style="height: 100%" class="hi"></div>
          <div style="height: 88%" class="hi"></div>
        </div>
        <div class="flex justify-between mt-2 mono text-[10.5px]" style="color: var(--ink3);"><span>apr 27</span><span>may 04</span><span>may 10</span></div>
      </div>
      <p class="muted">Three PRs are blocked on review: <a class="pill">#812</a> <a class="pill">#814</a> <a class="pill">#819</a>. Want me to suggest a temporary CODEOWNERS reshuffle?</p>`,
    sources: [
      {
        kind: "METRICS",
        items: [
          { t: "Review latency p50", d: "billing-svc · 6h → 38h" },
          { t: "Reviewer concentration", d: "2 reviewers · 84% of approvals" },
        ],
      },
      {
        kind: "PULL REQUESTS",
        items: [
          { t: "#812 · webhook idempotency", d: "9d in review" },
          { t: "#814 · invoice generator refactor", d: "8d in review" },
          { t: "#819 · dunning v2 dispatcher", d: "7d · changes requested" },
        ],
      },
      {
        kind: "DEVS",
        items: [
          { t: "Marcus Chen", d: "@marcus · on PTO" },
          { t: "Priya Nair", d: "@priya · on call" },
        ],
      },
    ],
    followups: [
      "Suggest a CODEOWNERS reshuffle",
      "Show the three blocked PRs",
      "Compare to last sprint",
    ],
  },
  "Find every place we still call stripe.charge() — are they still active?": {
    tools: [
      'git grep -n "stripe.charge(" HEAD',
      "Reading 4 matched files",
      "Cross-referencing prod traffic last 30d",
      "Composing audit",
    ],
    answer: () => `
      <p>Five call sites remain. Three are reachable from production code paths; two are inside tests or feature-flagged branches that haven't shipped in 6+ months.</p>
      <div class="codeblock my-3">
        <div class="flex items-center justify-between mb-3 opacity-60"><span>git grep -n "stripe.charge(" HEAD</span><span>5 results · 4 files</span></div>
        <div class="space-y-1.5">
          <div><span style="color:#7AAE6A">apps/billing/src/legacy/checkout.ts</span><span style="opacity:.5">:142</span> &nbsp;<span style="opacity:.85">await stripe.charge({ amount, source }) // ACTIVE — fallback path, ~30/day</span></div>
          <div><span style="color:#7AAE6A">apps/billing/src/legacy/checkout.ts</span><span style="opacity:.5">:217</span> &nbsp;<span style="opacity:.85">stripe.charge({ amount, source: token })   // ACTIVE — admin refund flow</span></div>
          <div><span style="color:#7AAE6A">apps/api/src/jobs/retry-charge.ts</span><span style="opacity:.5">:58</span>  &nbsp;<span style="opacity:.85">return stripe.charge({ amount, source: src }) // ACTIVE — retry queue</span></div>
          <div><span style="color:#E5B341">apps/billing/test/legacy.spec.ts</span><span style="opacity:.5">:33</span>   &nbsp;<span style="opacity:.65">stripe.charge({ amount: 100, source: 'tok' }) // test fixture</span></div>
          <div><span style="color:#E5B341">apps/api/src/experimental/dunning.ts</span><span style="opacity:.5">:91</span> &nbsp;<span style="opacity:.65">if (FLAG_DUNNING_V2_OFF) stripe.charge(…) // dead since 2024-11</span></div>
        </div>
      </div>
      <p class="muted">The retry queue path is the riskiest to migrate &mdash; it serves dunning fallback and runs ~120 times/day. Want me to draft the migration PR?</p>`,
    sources: [
      {
        kind: "FILES",
        items: [
          { t: "apps/billing/src/legacy/checkout.ts", d: "2 references · :142 :217" },
          { t: "apps/api/src/jobs/retry-charge.ts", d: "1 reference · :58" },
          { t: "apps/billing/test/legacy.spec.ts", d: "1 reference · test fixture" },
          { t: "apps/api/src/experimental/dunning.ts", d: "1 reference · feature-flagged" },
        ],
      },
      {
        kind: "METRICS",
        items: [{ t: "Active call rate", d: "~150/day across 3 paths" }],
      },
    ],
    followups: [
      "Draft the migration PR",
      "Who last touched these files?",
      "Open the dead-code references",
    ],
  },
};

export function askFallback(question: string): AskAnswer {
  return {
    tools: [
      "Understanding question intent",
      "Pulling relevant metadata",
      "Composing answer with citations",
    ],
    answer: () =>
      `<p>Here's what I'd return for <span class="italic-serif">"${question}"</span> &mdash; in your live workspace I'd cite specific PRs, files, and authors here.</p><p class="muted">Try one of the suggested questions to see a real walkthrough with sources.</p>`,
    sources: [],
    followups: ["What did we ship last week?", "Why is the billing repo slow?"],
  };
}

export const ROUTE_TITLES: Readonly<Record<string, string>> = {
  dashboard: "Dashboard",
  leaderboard: "Developers",
  repos: "Repos",
  "repo-detail": "billing-svc",
  ask: "Ask anything",
  digest: "Weekly digest",
  alerts: "Alerts",
  activity: "Recent activity",
  settings: "Settings",
  profile: "Profile",
};
