# Config

Centralize tunables in named constants (with env overrides where operators need them). Document *why* a default exists, not only *what* it is.

## What NOT to do

Do not scatter temperatures, URLs, or turn limits across UI, client, and agent code.

```bad-example
# temperature=0.2 sprinkled at every call site
_call_ollama(prompt, stream=True, temperature=0.2, ...)
_call_ollama(prompt, stream=False, temperature=0.2, ...)
# evals/evaluate_real_world_questions.py
query_ollama_once(..., temperature=0.2)
```

```bad-example
# Duplicated Ollama base URLs — drift when port or host changes
# app.py
requests.get("http://localhost:11434/api/tags", ...)
# astro_agent/llm/client.py
OLLAMA_URL = "http://localhost:11434/api/generate"
# astro_agent/agent/loop.py
OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
# astro_agent/rag/config.py
OLLAMA_EMBED_URL = "http://localhost:11434/api/embeddings"
```

## What to do

Define named constants in `astro_agent/llm/config.py` or `astro_agent/rag/config.py`, allow env overrides, and comment the rationale (model: `MAX_AGENT_TURNS`).

```good-example
# astro_agent/llm/config.py — single place for generation defaults
import os

OLLAMA_HOST = os.environ.get("ASTRO_OLLAMA_HOST", "http://localhost:11434")
OLLAMA_GENERATE_URL = f"{OLLAMA_HOST}/api/generate"
OLLAMA_CHAT_URL = f"{OLLAMA_HOST}/api/chat"

# Domain answers stay deterministic enough for evals; raise only for creative rewrites.
DEFAULT_TEMPERATURE = float(os.environ.get("ASTRO_TEMPERATURE", "0.2"))
```

```good-example
# astro_agent/rag/config.py — already the pattern for RAG
OLLAMA_EMBED_URL = os.environ.get(
    "ASTRO_OLLAMA_EMBED_URL",
    "http://localhost:11434/api/embeddings",
)

# Favor dense+RRF ordering after ref_id dedupe so full-book noise does not
# swamp the correct house-specific verse.
PRE_RERANK_WEIGHT = 0.18
```

```good-example
# Model for agent-loop turn budget (astro_agent/agent/loop.py today; prefer llm/config.py)
# Cap tool-call rounds so a stuck model falls back to the linear path instead of looping forever.
MAX_AGENT_TURNS = int(os.environ.get("ASTRO_MAX_AGENT_TURNS", "4"))
```
