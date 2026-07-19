# Testing

Prove new logic with fast unit tests. Use evals as quality gates, not as the only correctness check. Keep CI green under `ASTRO_CI=1`.

## What NOT to do

Do not ship chart/RAG math that is only “validated” by a full Ollama eval run, or leave new heuristics untested.

```bad-example
# Added resolve_window() / build_timing_report() but no tests/test_timing_*.py
# “We'll catch regressions in evaluate_career.py tonight.”

# New house-lord combo bonus in RAG rerank — only checked by eyeballing eval_rag JSON
CHAPTER_HINT_WEIGHT = 0.14  # no fixture asserting gold verse rises after bonus
```

```bad-example
# Agent tool test that hits a live Ollama server (fails offline / flakes in CI)
def test_agent_calls_get_timing_window():
    result = run_agent_loop(features, "Will next 6 months be good?")
    assert "Antardasha" in result
```

## What to do

Add unit tests with fixtures for chart and RAG heuristics. Mock Ollama for agent/tool paths. Treat evals as quality gates after units pass. Ensure `ASTRO_CI=1` pytest stays green.

```good-example
# tests/test_timing_tool.py — pure timing math, no LLM
def test_build_timing_report_counts_days_until_antardasha_end(sample_features):
    report = build_timing_report(sample_features, window_text="next 6 months", as_of_date="2024-06-01")
    assert report["days_until_antardasha_end"] is not None
    assert report["window_start"] <= report["window_end"]
```

```good-example
# tests/test_rag_antardasha_entity.py — fixture chart_facts, assert entity extraction
def test_query_entities_include_antardasha_lord(chart_facts):
    entities = _query_entities("career and profession", chart_facts)
    assert chart_facts["_antardasha_lord"].lower() in {e.lower() for e in entities}
```

```good-example
# Mock Ollama for agent tools; do not require a local server in CI
def test_tool_get_timing_window_returns_json(monkeypatch, sample_features):
    monkeypatch.setattr("astro_agent.agent.loop.requests.post", fake_ollama_tool_round)
    out = _tool_get_timing_window(sample_features, {"window_text": "next 6 months"})
    assert json.loads(out)["horizon_days"] >= 0
```

```good-example
# Layers of assurance
# 1) pytest tests/          — correctness of chart/RAG/utils (CI: ASTRO_CI=1)
# 2) evals/*.py             — quality gates (keyword/template/retrieval) on demand
# 3) CI must stay green:    ASTRO_CI=1 pytest tests/ -v --tb=short
```
