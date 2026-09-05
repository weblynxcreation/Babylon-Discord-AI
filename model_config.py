"""
Single source of truth for which NVIDIA NIM chat model this bot uses.

Pinned deliberately (not read from an environment variable) after this repo
shipped with the model getting swapped around ad hoc — including once to a
vision model that didn't reliably emit tool calls, silently breaking search,
image/GIF gen, code packaging, and the Capital Rift wiki tools. Every one of
those features depends on function/tool calling working correctly, so the
model is not something that should be casually reconfigured per deployment.

Current pin: openai/gpt-oss-20b
  https://build.nvidia.com/openai/gpt-oss-20b
  - OpenAI open-weight model, NIM-hosted, OpenAI-compatible chat/completions.
  - Native function/tool calling support (agentic-focused design).
  - 21B params (3.6B active, MoE) — small and fast relative to the
    70B/90B+ options previously listed here, while still supporting tools.

If you ever need to change this, update it here only, and then re-run
tests/test_agent_obsidian_integration.py plus a manual check that a message
like "what's today's date" actually triggers web_search — some backends
serving gpt-oss models have had inconsistent tool-calling behavior depending
on how they're deployed, so don't assume it works without checking.
"""

CHAT_MODEL = "openai/gpt-oss-20b"
