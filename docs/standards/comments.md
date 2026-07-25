# Comments

Document modules and non-obvious helpers. Prefer rationale over narration. Heuristics and magic numbers need a one-line *why*.

## What NOT to do

Avoid restating the next line, leaving helpers silent, or dropping unexplained constants.

```bad-example
# Increment the counter
turns_taken += 1

# Call Ollama
resp = requests.post(OLLAMA_CHAT_URL, json=payload, timeout=(10, timeout_s))
```

```bad-example
# Undocumented helper — callers cannot tell when to use it
def _house_effect_chapter_hints(question, chart_facts, intent=None):
    hints = set()
    ...
```

```bad-example
# Magic constant with no rationale
ENTITY_WEIGHT = 0.12
PRE_RERANK_WEIGHT = 0.18
```

## What to do

Use a module docstring that states purpose and strategy (see `astro_agent/rag/search.py` and `astro_agent/rag/config.py`). Docstring public APIs and non-trivial private helpers. Put rationale next to heuristics.

```good-example
"""Retrieval module for the RAG pipeline.

`search()` is the only public entry point. Given a user question, an
intent (from intent_router), and optional chart facts, it returns the
top-k most relevant chunks from the local Chroma index. Strategy:

1. Multi-query expansion ...
2. Per-query dense retrieval ...
3. Optional BM25 + RRF ...
"""
```

```good-example
"""Central configuration for the RAG pipeline (Phase 4 v0).

Single source of truth for embedding endpoint, Chroma settings, chunking
targets, reranker weights, and the entity/intent regex banks used at
ingest time. Everything tunable lives here so evaluate_rag.py can sweep
weights without touching pipeline code.
"""
```

```good-example
def _house_effect_chapter_hints(question, chart_facts, intent=None):
    """Collect Sharma Vol.1 house-effects chapter numbers hinted by the question or chart."""
    ...

# Favor dense+RRF ordering after ref_id dedupe so full-book noise (e.g. broad
# "effects" chapters) does not swamp the correct house-specific verse.
PRE_RERANK_WEIGHT = 0.18
```
