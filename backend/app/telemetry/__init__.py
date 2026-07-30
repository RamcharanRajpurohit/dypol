"""Telemetry — measurement primitives that are deliberately domain-free.

Everything in this package is written to be lifted out of DyPol wholesale into
the standalone ``adaptive-runtime`` library (FUTURE_PLAN §5) without edits:
nothing here imports from ``app.agents``, ``app.services``, or any GitHub- or
Mongo-specific module. Depend on it in that direction only.

  * ``cost``  — per-provider token pricing → ``cost_usd``.

This is the reward signal the plan's Phase 3 bandit trains against
(``reward = quality − λ·cost − μ·latency``), so it has to exist and be
trustworthy before any policy work starts.
"""
