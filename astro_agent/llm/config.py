"""Central LLM / Ollama runtime configuration.

Tunable sampling, timeouts, context windows, and endpoint URLs live here so
call sites do not scatter magic numbers. Override via environment variables
where noted (same pattern as ``astro_agent.rag.config``).
"""

from __future__ import annotations

import os


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.environ.get(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


# Base host for all Ollama HTTP APIs (generate / chat / embeddings).
OLLAMA_HOST = (os.environ.get("ASTRO_OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
OLLAMA_GENERATE_URL = f"{OLLAMA_HOST}/api/generate"
OLLAMA_CHAT_URL = f"{OLLAMA_HOST}/api/chat"
OLLAMA_EMBED_URL = f"{OLLAMA_HOST}/api/embeddings"
OLLAMA_TAGS_URL = f"{OLLAMA_HOST}/api/tags"

MODEL_NAME = "qwen2.5:7b-instruct"
DEEP_MODEL_NAME = "deepseek-r1:14b"

# Default generation sampling — low for factual astrology answers.
DEFAULT_TEMPERATURE = 0.2
# Slightly warmer rewrite pass for chat polish (humanizer).
HUMANIZER_TEMPERATURE = 0.4
# Deterministic summarization / intent classification.
SUMMARIZE_TEMPERATURE = 0.0
INTENT_CLASSIFIER_TEMPERATURE = 0.0

DEFAULT_TIMEOUT_S = 120
DEFAULT_NUM_CTX = 16384
# Floors applied in resolve_ollama_config so misconfigured env cannot starve the call.
MIN_TIMEOUT_S = 15
MIN_NUM_CTX = 1024
# Connect timeout for the HTTP handshake (separate from read/generate timeout).
HTTP_CONNECT_TIMEOUT_S = 10

# Conversation buffer summarizer.
SUMMARIZE_NUM_CTX = 4096
SUMMARY_MAX_WORDS = 150
# Intent classifier small-model context.
INTENT_CLASSIFIER_NUM_CTX = 4096
INTENT_CLASSIFIER_TIMEOUT_S = 45

# CLI / debug prompt preview length.
PROMPT_PREVIEW_CHARS = 1200

# Agent ReAct loop turn budget (env-overridable).
MAX_AGENT_TURNS = int(os.environ.get("ASTRO_MAX_AGENT_TURNS", "4"))
