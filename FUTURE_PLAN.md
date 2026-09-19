# FUTURE PLAN — from DyPol to **AdaptiveRuntime**

**Author:** Ramcharan Rajpurohit
**Written:** 2026-07-29
**Status:** proposal / design doc — nothing here is built yet
**Related doc:** `~/Documents/Ramcharan/BTP_2026_Project_Repos.md` (topic survey + repo research)

---

## 0. What this document is

A plan to evolve this codebase into a **BTP-grade research artifact plus a working product**, by extracting its agent-orchestration layer into a standalone, benchmarkable library and replacing its hand-written resource heuristics with a *learned* policy.

It merges four of the proposed BTP topics into one coherent system:

| Topic | Role in this plan |
|---|---|
| **DS3 — Resource-aware agents** | The core contribution: a per-step policy over four resource axes |
| **DS2 — Small + large agent collaboration** | The model-selection axis (cheap vs strong), already physically present here |
| **DS6 — Agent evaluation** | The measurement spine, and the fallback deliverable if the policy underperforms |
| **DS1 — Self-improving agents** | The learning loop: the policy updates from its own execution traces |

**Explicitly out of scope:** DS4 (compression) and DS5 (model merging) — both require A100-class GPUs and neither connects to this codebase.

---

## 1. The thesis in one paragraph

This codebase already decides, on every turn, *which model to use, how many tool turns to allow, how much history to keep, and which sub-agents to expose.* Every one of those decisions is currently a **hard-coded constant or a hand-written role table**. The thesis is that these four decisions are jointly learnable from execution traces as a contextual bandit conditioned on predicted task difficulty, that doing so yields a materially better cost/quality frontier than the hand-tuned baseline, and that the resulting policy generalises off this product onto public agent benchmarks.

The hand-written baseline is not a weakness — it is the **expert control arm** the learned policy must beat, and it was tuned against real usage. That is a much stronger experimental design than routing-vs-random.

---

## 2. Current state audit

Measured 2026-07-29. ~18,100 lines of Python + TypeScript. Backend is FastAPI + LangGraph; frontend is Next.js.

### 2.1 The agents package (`backend/app/agents/`, ~2,400 lines)

| File | Lines | What it does |
|---|---|---|
| `graph.py` | 486 | LangGraph state machine: `START → prepare → agent → (tools → agent)* → END`. Provider fallback is an in-node `while` loop over `model_chain()`. |
| `tools.py` / `general_tools.py` | 275 / 264 | Tool definitions bound per call |
| `providers.py` | 270 | Provider registry, model factory, role policy, fallback chain, quota detection |
| `prompts.py` / `subagent_prompts.py` | 247 / 112 | System prompt construction |
| `registry.py` | 206 | Builds `delegate_*` sub-agent tools (agent-as-tool pattern) |
| `memory.py` | 202 | Mongo↔LangChain message mapping, `trim_history()`, `summarize_overflow()` |
| `base.py` | 186 | Reusable bounded tool-calling loop for sub-agents |
| `trace.py` | 110 | Custom tool executor that records the full `ChatToolCall` trace |
| `guardrails.py` | 98 | Prompt-injection defence for untrusted external content |
| `observability.py` | 82 | Langfuse tracing — usage, latency, cost, LLM-as-judge, offline regression evals |
| `budget.py` | — | `DelegationBudget`: `max_depth`, `max_delegations`, `global_tool_cap` |
| `subagents/` | 328 | `code_analyst`, `pr_activity_analyst`, `web_researcher`, `synthesizer` |

### 2.2 The four axes — all present, all static

This is the central finding of the audit.

| Axis | Current implementation | Why it's the target |
|---|---|---|
| **Model** | `providers.py:155-160` — `_ROLE_POLICY = {"router": (…, True), "analyst": (…, False), "web": (…, True), "synth": (…, False)}`. Bool = "use the cheap model". | A **static role→tier table**. It never looks at the query. `model_chain()` is purely *reactive* — it swaps model only *after* a quota error, never predicts difficulty up front. |
| **Reasoning effort** | `core/config.py:64-65` — `agent_max_tokens: 1200`, `agent_max_tool_turns: 6` | Two global constants applied identically to "how many PRs merged last week" and "why did the auth refactor break billing". |
| **Memory depth** | `memory.py` — `trim_history()` against `agent_history_token_budget: 12000`; plus `rag/retriever.py` fixed top-k | A fixed token budget regardless of whether history is relevant to the current question. |
| **Tool scope** | `registry.py:95` `build_delegate_tools()` + `chat_tools.available_tool_names()` | Filtered by *availability* (is GitHub connected?), never by *usefulness for this query*. Every tool schema in the bind costs input tokens on every turn. |

There is also already a **static resource budget** in `budget.py` (`max_depth=1`, `max_delegations=3`, `global_tool_cap=24`) — a hand-set version of exactly what the policy should be setting per query.

### 2.3 What exists that de-risks the project enormously

- **`trace.py` + `TraceCollector`** — a flat, ordered record of every tool call including nested sub-agent calls. *This is the bandit's training data, already being collected.*
- **`observability.py`** — Langfuse already wired for usage/latency/cost + LLM-as-judge + offline regression evals. The measurement plumbing exists.
- **`services/governance.py`** — logs model + token estimate + latency with secret/PII redaction.
- **A real small model already configured** — `groq:openai/gpt-oss-20b` appears as an example spec. The small-vs-large split (DS2) is physically present, not hypothetical.
- **Four providers wired** — groq, gemini, anthropic, openai — so cross-provider arms are free.

### 2.4 Gaps

- ~~**No tests at all.**~~ **CLOSED 2026-07-30.** `backend/tests/` — 54 tests, green, no network or Mongo. Covers the cost table, the four axes as they stand today (characterization tests for the Phase-2 behaviour-preserving refactor), and regressions for bugs that actually shipped. Mutation-checked: deliberately breaking the pricing logic fails the suite.
- ~~**No cost accounting per turn**~~ **CLOSED 2026-07-30.** `app/telemetry/cost.py` + `TraceCollector.record_model_call()` / `.usage_summary()` put a real `cost_usd`, token counts and `latency_ms` on every model call. Verified live: an 11-in/960-out Gemini turn costs $0.0024033. Unknown models report `priced=False` rather than $0, so a partial total can't masquerade as a complete one.
- **No difficulty signal** anywhere in the codebase. *(still open — Phase 3)*
- **No offline replay** — you cannot currently re-run a past trace against a different policy. *(still open — Phase 1)*

---

## 3. Blockers to clear before anything else

> These are not optional and they come first.

### 3.1 🔴 URGENT — a live GitHub App private key is sitting in the working tree

```
backend/dypolai.2026-05-10.private-key.pem
backend/.env
backend/.env.bak.1780164024
web/.env.local
```

The project is **not under version control** (`git status` → `fatal: not a git repository`). The moment this is `git init`-ed and pushed as a BTP artifact, that private key is published. Rewriting history afterwards does not help — forks, clones and caches keep it.

**Actions, in order:**
1. Rotate/regenerate the GitHub App private key on GitHub. Assume the current one is burned.
2. Write `.gitignore` covering `*.pem`, `.env*`, `!.env.example`, `.chroma/`, `.ruff_cache/`, `*.egg-info/`, `.venv/`, `node_modules/`.
3. Move the key out of the repo entirely — load from an env var or a path outside the tree.
4. *Only then* `git init` and make the first commit.

### 3.2 Version control

No git history means no evidence of incremental work for a BTP evaluation, and one bad `rm` costs the whole project. Fix immediately after 3.1.

### 3.3 Pick one name

Settled: the product is **DyPol** (**DyPol.ai** in full), and **AdaptiveRuntime** is the library. Python package `dypol_backend` and GitHub App `dypolai` already match. The checkout directory has been renamed to `dypol`, so no aliases remain.

---

## 4. Research foundation

Everything below was looked up on 2026-07-29 against current sources. Anything marked **⚠** contradicts what a model would produce from memory and must not be coded from recall.

### 4.1 ⚠ Reasoning-effort control is now categorical and provider-specific

This materially changes the design of the effort axis. The "token budget" mental model is **obsolete on current frontier models**.

| Provider | Current parameter | Values | Source |
|---|---|---|---|
| **Anthropic** | `thinking: {type: "adaptive"}` | `budget_tokens` is **deprecated** on Opus 4.6 / Sonnet 4.6, and **disabled** on Opus 4.7+ and Sonnet 5 — passing it returns HTTP 400 | [Extended thinking docs](https://platform.claude.com/docs/en/build-with-claude/extended-thinking) |
| **Google** | `thinking_level` (Gemini 3+); `thinking_budget` only on pre-Gemini-3 | `LOW` / `MEDIUM` / `HIGH` | [Gemini thinking](https://ai.google.dev/gemini-api/docs/thinking), [Gemini 3 guide](https://ai.google.dev/gemini-api/docs/gemini-3) |
| **OpenAI** | `reasoning.effort` | `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max` (model-dependent); gpt-5.5 defaults to `medium` | [Reasoning guide](https://developers.openai.com/api/docs/guides/reasoning) |

**Design consequence:** the effort axis must be a small ordinal ladder (`{none, low, medium, high}`) with a **per-provider adapter** mapping ladder rungs onto whatever that provider actually accepts, plus a capability probe, because Anthropic will hard-error on the old parameter. Do **not** model this axis as a token count.

Note also that `agent_max_tool_turns` is a *second, independent* effort dial that this codebase already owns and that works uniformly across providers. It is the safer one to start with.

### 4.2 Routing and cost-aware selection

| Work | Relevance |
|---|---|
| [Dynamic Model Routing and Cascading for Efficient LLM Inference: A Survey](https://arxiv.org/pdf/2603.04445) | Start here — the 2026 survey that frames the whole field |
| [Online Multi-LLM Selection via Contextual Bandits Under Unstructured Context Evolution](https://arxiv.org/abs/2506.17670) (AAAI 2026) | **Closest prior art to the proposed method.** LinUCB with provable sublinear myopic regret, plus budget-aware and position-aware extensions. Read before designing the policy. |
| [Correlation-Aware Contextual Bandits with Surrogate Rewards for LLM Routing](https://arxiv.org/abs/2607.09015) | Handles correlated arms + noisy surrogate reward — directly applicable, since our reward comes from an LLM judge |
| [BEST-Route](https://arxiv.org/abs/2506.22716) / [microsoft/best-route-llm](https://github.com/microsoft/best-route-llm) | Joint selection of *model* **and** *number of samples*; ~60% cost cut at <1% quality drop |
| [Learning to Route LLMs from Implicit Cost-Performance Preferences via Meta-Learning](https://arxiv.org/pdf/2606.06178) | Alternative to bandits if online exploration proves too expensive |
| [lm-sys/RouteLLM](https://github.com/lm-sys/RouteLLM) | Canonical baseline to reproduce. **Dormant since Aug 2024** — reproduce, cite, exceed. |
| [vllm-project/semantic-router](https://github.com/vllm-project/semantic-router) | Current production frontier; routes model **and** reasoning effort. The system to differentiate against. |
| [MilkThink-Lab/Awesome-Routing-LLMs](https://github.com/MilkThink-Lab/Awesome-Routing-LLMs) | Maintained reading list |

### 4.3 Adaptive retrieval (the memory-depth axis)

| Work | Relevance |
|---|---|
| [Adaptive-RAG](https://arxiv.org/abs/2403.14403) | **The template for this axis.** A lightweight classifier labels a query A/B/C — no-retrieval / single-step / multi-step — exactly the ordinal structure we want. |
| Self-RAG | Model emits reflection tokens deciding *when* to retrieve and critiquing what came back |
| [DynamicRAG](https://arxiv.org/pdf/2505.07233) | RL-trained reranker that chooses *k* per query |
| Adaptive-k | Chooses *k* from the retrieval score distribution with no added latency — cheapest thing to try first |
| [L-RAG: Entropy-Based Lazy Loading](https://arxiv.org/pdf/2601.06551) | Entropy as a retrieve/don't-retrieve trigger |

### 4.4 Evaluation

| Resource | Relevance |
|---|---|
| **[Inspect AI Agent Bridge](https://inspect.aisi.org.uk/agent-bridge.html)** | **The single biggest de-risking finding — now measured, see §7.** `agent_bridge()` patches the OpenAI, Anthropic **and `google-genai`** async client internals so any model named `"inspect"` is redirected into Inspect's model API, meaning this LangGraph agent can be evaluated inside Inspect without being rewritten. `sandbox_agent_bridge()` covers containerised agents via a proxy on `localhost:13131`. On `forward_generation_config`: it defaults to `False`, which drops `max_tokens`/reasoning settings. Upstream advises leaving it `False` so a scaffold's own tuning doesn't distort cross-model comparison — but for *this* project those params are the treatment variables, so we set `True` and accept that our numbers measure the policy, not the bare model. State that choice explicitly in the report. |
| [Inspect custom agents](https://inspect.aisi.org.uk/agent-custom.html) | For the parts the bridge can't cover |
| [UKGovernmentBEIS/inspect_ai](https://github.com/UKGovernmentBEIS/inspect_ai) | 2.4k★, 410 MB, active. The harness. |
| [sierra-research/tau-bench](https://github.com/sierra-research/tau-bench) | Tool-agent-user multi-step dialogue with domain policies — closest benchmark to what this product actually does |
| [SWE-bench](https://github.com/SWE-bench/SWE-bench) (Lite subset) | Code-reasoning arm; execution-graded, so no judge noise |
| [harbor-framework/terminal-bench](https://github.com/harbor-framework/terminal-bench) | Hard multi-step terminal tasks, container-verified |
| [princeton-pli/hal-harness](https://github.com/princeton-pli/hal-harness) | Standardised cross-benchmark runner with built-in cost tracking |

### 4.5 Bandit implementations

| Library | Notes |
|---|---|
| [david-cortes/contextualbandits](https://github.com/david-cortes/contextualbandits) | Cython-accelerated LinUCB, batch/streaming fitting. Best default. |
| [MABWiser](https://pypi.org/project/mabwiser/) | Fidelity's library; context-free + parametric + non-parametric, built-in parallelism, well documented |
| [Vowpal Wabbit](https://vowpalwabbit.org/tutorials/contextual_bandits.html) | Industrial-strength online learning; steeper learning curve, best if we go fully online |
| [singhsidhukuldeep/contextual-bandits](https://github.com/singhsidhukuldeep/contextual-bandits) | LinUCB, ε-greedy, UCB, Thompson, KernelUCB, NeuralLinear, DecisionTree — useful for ablating algorithms |

**Algorithm choice:** start with **LinUCB** — deterministic, auditable, easy to debug, and it matches the AAAI-2026 prior art so results are comparable. Keep **Thompson sampling** as the ablation arm; it's more robust under non-stationarity and delayed feedback, both of which we have.

### 4.6 Memory / self-improvement reference implementations

[letta-ai/letta](https://github.com/letta-ai/letta) (24.0k★) for self-editing memory; [EvoAgentX](https://github.com/EvoAgentX/EvoAgentX) (3.2k★) for workflow-level self-evolution; [getzep/graphiti](https://github.com/getzep/graphiti) (29.3k★) for bi-temporal invalidation of stale facts; [microsoft/agent-lightning](https://github.com/microsoft/agent-lightning) (17.4k★) if we later want to *train* the small model rather than just route to it.

---

## 5. Target architecture

Do **not** bolt this into DyPol as a feature. DyPol's tools are GitHub/RAG-specific, so it cannot run τ-bench as-is, and without public benchmarks the research claim is not credible. Split it:

```
adaptive-runtime/                 ← BTP artifact: standalone, domain-free, benchmarkable
  runtime/
    policy/
      features.py                 ← difficulty featurisation
      bandit.py                   ← LinUCB / Thompson over the joint action space
      baselines.py                ← always-strong, always-cheap, role-table, RouteLLM-style
    axes/
      model.py                    ← cheap ↔ strong ↔ cross-provider
      effort.py                   ← ordinal ladder + per-provider adapter (see §4.1)
      memory.py                   ← history budget + retrieval depth
      tools.py                    ← tool-scope selection
    telemetry/
      trace.py                    ← generalised from app/agents/trace.py
      cost.py                     ← per-provider token pricing → cost_usd
      replay.py                   ← offline re-scoring of past traces
    adapters/
      langgraph.py                ← binds a policy to a LangGraph node
      inspect_bridge.py           ← agent_bridge(forward_generation_config=True)

dypol/                         ← first real consumer + case study
  backend/app/agents/providers.py ← _ROLE_POLICY replaced by runtime.policy.decide()
  backend/app/agents/graph.py     ← reads the decision from AgentState
  backend/app/agents/budget.py    ← DelegationBudget populated by the policy, not constants
```

### Why the split is strictly better than either half alone

1. The library is clean, domain-free and open-sourceable — a proper BTP deliverable.
2. DyPol becomes **real-world validation**. Almost no student router has this. Everyone reports benchmark numbers; we can report benchmark numbers *plus* cost-per-query on a live application.
3. DyPol **generates the traces** needed to train the bandit. Greenfield, they'd have to be synthesised.
4. Clean IP separation from employer work — public benchmarks and a personal side project only.
5. Two CV lines instead of one.

---

## 6. The four axes, designed

The joint action space is deliberately kept small so a linear bandit can learn it from realistic trace volumes.

| Axis | Arms | Where it binds | Notes |
|---|---|---|---|
| **Model** | `{cheap, strong}` × enabled providers | `providers.build_model()` | Start with 2 tiers on 1 provider; expand to cross-provider once the reward signal is trustworthy |
| **Effort** | `{none, low, medium, high}` | new per-provider adapter + `agent_max_tool_turns` | Ordinal, **not** a token count (§4.1). Start with tool-turn cap only — provider-uniform and already implemented. |
| **Memory depth** | `{0, short, full}` history × `{0, k_small, k_large}` retrieval | `memory.trim_history()`, `rag/retriever.py` | Adaptive-RAG's A/B/C labelling is the template |
| **Tool scope** | `{core, +delegates, all}` | `registry.build_delegate_tools()` | Fewer bound tools = fewer input tokens *every turn*; likely the cheapest win in the whole system |

**Total action space:** 2 × 4 × 9 × 3 = 216 combinations — too many for independent arms. Model it as a **linear bandit over a factored action encoding** (one-hot per axis + interaction terms), not as 216 discrete arms. This is the main methodological decision in the project and should be justified explicitly in the report.

### Difficulty features (the context vector)

Cheap to compute, no LLM call:
- Query length, token count, question type (embedding-classified)
- Presence of code/identifiers/entities in the query
- Conversation depth, whether history is topically continuous
- Retrieval score distribution (max, mean, entropy) — free, we already retrieve
- Workspace size proxies (repo count, index size)
- Historical: rolling success rate for similar queries

### Reward

```
reward = quality − λ·normalised_cost − μ·normalised_latency
```

- `quality` — execution-graded where possible (SWE-bench, terminal-bench), LLM-judge elsewhere (τ-bench, DyPol). Judge noise is real; §4.2's surrogate-reward paper addresses it.
- `λ`, `μ` — swept, to produce a **Pareto frontier** rather than one number. Report the frontier; a single operating point invites "you just picked a favourable λ".

---

## 7. Evaluation design

**Benchmarks:** τ-bench (primary — closest to a tool-using assistant), SWE-bench-Lite subset (execution-graded, no judge noise), terminal-bench (hard multi-step), plus DyPol's own held-out query set (real-world arm).

**Baselines** — all four, always reported:
1. **Always-strong** — quality ceiling, cost ceiling
2. **Always-cheap** — cost floor
3. **`_ROLE_POLICY`** — *the hand-tuned expert baseline already shipped in this repo.* The most interesting comparison and the one reviewers will care about.
4. **RouteLLM-style binary router** — published prior art

**Metrics, reported jointly and never separately:** task success rate · cost per task (USD) · p50/p95 latency · tokens in/out · tool calls per task. Plus per-axis ablations: which axis actually carries the gain? A plausible and publishable outcome is *"tool-scope selection accounts for most of the saving; model routing is overrated"* — that would be a genuinely useful negative result.

**Integration risk — RESOLVED 2026-07-30 (was the plan's top technical unknown).** Tested empirically against inspect-ai 0.3.251 / langchain-google-genai 4.3.2 / langchain-groq 1.1.3 by running a real bridged `eval()` against `mockllm/model`:

| Path | Bridged? | Evidence |
|---|---|---|
| `langchain-google-genai` (Gemini) | **YES** — contradicts this plan's original assumption | langchain-google-genai 4.x depends on `google-genai`, which `agent_bridge()` patches at `BaseApiClient.async_request`. Returned `'Default output from mockllm/model'`. |
| `langchain-groq` (Groq) | **NO** | The `groq` SDK has its own `_base_client` that nothing patches. Produced a genuine 401 from api.groq.com. |
| sync calls (either provider) | **NO** | Only `AsyncAPIClient`/`async_request` are patched — `.invoke()` escapes to the real network. |
| streaming | **NO** | Hard-errors: `RuntimeError("Streaming not currently supported for agent_bridge()")`. |

**Decision:** keep `langchain-google-genai` for Gemini (already bridged); swap `langchain-groq` for `langchain-openai` pointed at Groq's OpenAI-compatible endpoint `https://api.groq.com/openai/v1` — verified intercepted, because the patch sits *above* transport so the base URL is irrelevant. One code path serves both prod and eval with no conditionals.

**Hard constraint this imposes on the eval path: the agent must be fully async and non-streaming.** Sync and streaming calls silently escape the bridge or hard-error. Today's `stream_agent()` therefore cannot be the evaluated path — `run_agent()` can. Smoke-test it by asserting one bridged sample returns `'Default output from mockllm/model'` through every provider the graph touches; that catches an escaped call before an eval run burns real keys.

One caveat found: on the Google path the `inspect/<provider>/<model>` target spec is **silently ignored** (google-genai puts the model in the URL path, but Inspect reads it from the request body), so it always falls back to the default eval model. Gemini's own OpenAI-compatible endpoint restores correct targeting if per-sample model pinning is ever needed.

---

## 8. Phased plan

Assumes two semesters, roughly Jul 2026 → May 2027.

### Phase 0 — Hygiene (week 1, non-negotiable) — **DONE 2026-07-30, except key rotation**
- [x] `.gitignore` at repo root + backend, covering `*.pem`, `.env*` (with `!.env.example`), `.chroma/`, caches
- [x] Private key moved out of the tree to `~/.config/dypol/` (mode 600) and `GITHUB_APP_PRIVATE_KEY_PATH` repointed; verified the app still loads it
- [x] `git init` + verified **zero** secrets would be tracked (`git check-ignore` confirms `.env`, `.env.bak.*`, `web/.env.local` are all ignored)
- [x] Pick one name — DyPol / DyPol.ai, §3.3
- [x] `pytest` + tests on `providers.model_chain()` and `memory.trim_history()` — and 52 more
- [ ] **Rotate the GitHub App private key on GitHub.** *Only the owner can do this.* The key was in the working tree for months; assume it is burned even though the tree was never pushed.
- [ ] First commit + push to a private repo *(deliberately left to the owner — nothing is staged)*

**Exit:** repo is under version control, contains no secrets, and has a green test run. **Met**, pending key rotation.

### Phase 1 — Instrumentation and measurement (weeks 2–8)
- Add `cost_usd` and `latency_ms` to every trace row (`telemetry/cost.py` with per-provider pricing)
- Generalise `trace.py` out of the GitHub domain
- Build `telemetry/replay.py` — re-score a stored trace under a different policy without re-running the agent
- Stand up Inspect AI on τ-bench + SWE-bench-Lite
- **Resolve the agent_bridge/Gemini-Groq question (§7)**
- Reproduce RouteLLM's reported numbers as a sanity check on the harness

**Exit (mid-Semester-1):** a working measurement system that can score *any* policy on ≥2 public benchmarks and on DyPol traces. **From this point the project cannot end empty-handed** — even total failure of the policy leaves a publishable evaluation harness.

### Phase 2 — Static axes + expert baseline (weeks 9–14)
- Extract the four axes into `runtime/axes/` behind one `PolicyDecision` dataclass
- Rewire DyPol to consume it, reproducing today's behaviour exactly (a pure refactor — traces must match)
- Implement the per-provider effort adapter with capability probing (§4.1)
- Measure all four baselines on all benchmarks

**Exit:** the hand-tuned baseline is quantified. We now know what must be beaten.

### Phase 3 — The learned policy (weeks 15–22)
- `policy/features.py` — difficulty featurisation
- `policy/bandit.py` — LinUCB over the factored action encoding; Thompson as ablation
- Train offline on collected traces via replay; then online in DyPol behind a flag
- Sweep λ/μ to produce the Pareto frontier

**Exit:** learned policy vs. all four baselines, on all benchmarks, with per-axis ablations.

### Phase 4 — Self-improvement loop + write-up (weeks 23–30)
- Close the DS1 loop: eval outcomes feed back into policy updates on a schedule; detect and handle distribution drift
- Guard against the known failure mode: a policy that improves on its own logged distribution and degrades off it. Hold out a frozen benchmark slice never used for updates.
- Write up, including negative results
- Open-source `adaptive-runtime`; keep DyPol private

**Exit:** BTP report, a public repo, and a defensible quantitative claim.

---

## 9. Risk register

| Risk | Severity | Mitigation |
|---|---|---|
| Leaked GitHub App private key published | **Critical** | Phase 0, before any git init. Rotate the key regardless. |
| `agent_bridge()` doesn't intercept Gemini/Groq | High | Verify in Phase 1; fall back to OpenAI-compatible endpoints or a provider shim |
| Learned policy fails to beat `_ROLE_POLICY` | Medium | Phase 1 harness is the standalone deliverable; a well-measured negative result on a hand-tuned baseline is publishable |
| Judge noise swamps the quality signal | Medium | Weight execution-graded benchmarks highest; apply the surrogate-reward treatment from [arXiv:2607.09015](https://arxiv.org/abs/2607.09015) |
| API costs exceed budget | Medium | Fixed benchmark subsets; aggressive caching; replay-based offline training instead of live rollouts; ask about department/Srijan credits early |
| Provider API churn breaks the effort axis mid-project | Medium | Capability probe + adapter layer; pin model versions; §4.1 already shows this churned once in 2026 |
| Refactor destabilises a working product | Medium | Phase 2 is a behaviour-preserving refactor with trace-equality tests before any policy change |
| Scope creep into all six DS topics | Medium | DS4/DS5 are explicitly excluded. Four axes, fixed. |

---

## 10. Resources, consolidated

### Code to build on
[inspect_ai](https://github.com/UKGovernmentBEIS/inspect_ai) · [tau-bench](https://github.com/sierra-research/tau-bench) · [SWE-bench](https://github.com/SWE-bench/SWE-bench) · [terminal-bench](https://github.com/harbor-framework/terminal-bench) · [hal-harness](https://github.com/princeton-pli/hal-harness) · [contextualbandits](https://github.com/david-cortes/contextualbandits) · [MABWiser](https://pypi.org/project/mabwiser/) · [Vowpal Wabbit](https://vowpalwabbit.org/tutorials/contextual_bandits.html) · [RouteLLM](https://github.com/lm-sys/RouteLLM) · [semantic-router](https://github.com/vllm-project/semantic-router) · [best-route-llm](https://github.com/microsoft/best-route-llm) · [litellm](https://github.com/BerriAI/litellm) · [letta](https://github.com/letta-ai/letta) · [EvoAgentX](https://github.com/EvoAgentX/EvoAgentX) · [graphiti](https://github.com/getzep/graphiti) · [agent-lightning](https://github.com/microsoft/agent-lightning)

### Papers
Routing survey [2603.04445](https://arxiv.org/pdf/2603.04445) · LinUCB multi-LLM selection, AAAI 2026 [2506.17670](https://arxiv.org/abs/2506.17670) · Correlation-aware bandits [2607.09015](https://arxiv.org/abs/2607.09015) · BEST-Route [2506.22716](https://arxiv.org/abs/2506.22716) · Meta-learned routing [2606.06178](https://arxiv.org/pdf/2606.06178) · Adaptive-RAG [2403.14403](https://arxiv.org/abs/2403.14403) · DynamicRAG [2505.07233](https://arxiv.org/pdf/2505.07233) · L-RAG [2601.06551](https://arxiv.org/pdf/2601.06551)

### Provider docs — re-check before coding, these churn
[Anthropic extended thinking](https://platform.claude.com/docs/en/build-with-claude/extended-thinking) · [Gemini thinking](https://ai.google.dev/gemini-api/docs/thinking) · [Gemini 3 guide](https://ai.google.dev/gemini-api/docs/gemini-3) · [OpenAI reasoning](https://developers.openai.com/api/docs/guides/reasoning) · [Inspect agent bridge](https://inspect.aisi.org.uk/agent-bridge.html) · [Inspect custom agents](https://inspect.aisi.org.uk/agent-custom.html)

### Reading lists
[Awesome-Routing-LLMs](https://github.com/MilkThink-Lab/Awesome-Routing-LLMs) · [awesome-adaptive-computation](https://github.com/koayon/awesome-adaptive-computation) · [Awesome-Efficient-Reasoning-LLMs](https://github.com/Eclipsess/Awesome-Efficient-Reasoning-LLMs) · [awesome-agent-harness](https://github.com/Picrew/awesome-agent-harness)

### Actual resource needs
**No GPU required.** Costs are API credits (the real budget line), a laptop, and Docker for terminal-bench/SWE-bench containers. Small models must be **hosted** (Groq, Gemini Flash, DeepSeek) — local Ollama on integrated graphics is too slow to sit inside a benchmark loop, and hosted endpoints make the ₹-per-token comparison more honest anyway.

---

## 11. Intended outputs

1. **`adaptive-runtime`** — public library with benchmark results and a reproducible harness
2. **DyPol** — private product running on it, as the real-world case study
3. **BTP report** — Pareto frontiers, per-axis ablations, negative results included
4. **Possible paper** — the four-axis joint policy is not, as far as this survey found, covered by existing work; the prior art routes *models* (and sometimes effort), not memory depth and tool scope jointly

### Target CV lines

> **AdaptiveRuntime** — Resource-Aware Agent Execution Layer
> - Built a per-step routing policy selecting model, reasoning effort, tool scope, and memory depth by predicted task difficulty, cutting agent cost **X%** at **<Y%** accuracy loss on τ-bench and SWE-bench-Lite.
> - Trained a LinUCB contextual bandit on production execution traces, beating a hand-tuned expert routing table deployed in a live product.
> - Shipped a reproducible evaluation harness on Inspect AI measuring cost, p95 latency, and task success jointly across **N** multi-step agent benchmarks.

---

## 12. Open questions to resolve before Phase 2

1. ~~Does `agent_bridge()` intercept `langchain-google-genai` / `langchain-groq`?~~ **ANSWERED 2026-07-30 — see §7.** Gemini yes, Groq no; Groq moves to its OpenAI-compatible endpoint. The real constraint is that the eval path must be async and non-streaming.
2. Is there enough real DyPol traffic to train a bandit, or must Phase 3 bootstrap from benchmark rollouts?
3. LinUCB over a factored action encoding, or a hierarchy of per-axis bandits? The factored form is cleaner; the hierarchy is easier to debug and ablate.
4. Does the effort axis stay in scope given provider churn (§4.1), or does v1 ship with tool-turn cap as the sole effort dial?
5. BTP supervisor's appetite for a systems-heavy vs theory-heavy framing — changes how much of Phase 3 is regret analysis versus engineering.
