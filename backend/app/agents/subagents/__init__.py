"""Runtime sub-agents — specialist agents the orchestrator delegates to.

These are *product runtime* agents (spawned per end-user question to answer
about a GitHub org), intentionally mirroring the .claude/agents dev-time
subagent concept (name, description, tool allowlist, model, system prompt)
but executed inside this FastAPI backend rather than by Claude Code.
"""
