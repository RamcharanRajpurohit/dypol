"""Agent layer — provider-agnostic LangGraph orchestration for DyPol AI.

This package replaces the two hand-written agent loops that used to live in
``services/chat.py`` with a single LangGraph state machine that can run on
ANY configured LLM provider (Claude / OpenAI / Gemini / Groq), selected at
runtime via LangChain's ``init_chat_model``.

Modules:
  * ``providers``  — provider registry, model factory, fallback chain.
  * ``prompts``    — system prompt + per-workspace prompt builder.
  * ``memory``     — Mongo→LangChain message mapping, history trimming,
                     running-summary context management.
  * ``trace``      — custom tool executor that captures the ChatToolCall
                     trace (name/args/preview/duration) the UI renders.
  * ``tools``      — LangChain StructuredTool wrappers over the existing
                     GitHub handlers + web search + RAG + sub-agent tools.
  * ``graph``      — the LangGraph agent (prepare → agent → tools → finalize).
  * ``budget``     — per-turn safety caps (tool turns, delegations).
  * ``tracing``    — TraceCollector that flattens nested sub-agent calls.
  * ``base``       — reusable bounded loop shared by sub-agents.
  * ``registry``   — builds the delegate_* sub-agent tools.
  * ``orchestrator``— top-level entry called by services/chat.py.
  * ``subagents/`` — the specialist runtime agents.
"""
