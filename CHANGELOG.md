# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Added
- `astro_agent/` package with domain sub-packages (`chart/`, `llm/`, `rag/`, `routing/`, `agent/`, `utils/`)
- `evals/` directory consolidating all evaluation harnesses (`evaluate_*.py`, `eval_*.py`, `run_pr1_acceptance_watch.py`)
- `docs/` directory with moved planning docs (`RAG_PLAN.md`, `AGENT_PROD_PLAN.md`, `FUTURE_IMPROVEMENTS.md`)
- `requirements-dev.txt` for developer tooling (ruff, mypy, PyMuPDF)
- `pyproject.toml` with ruff linter/formatter config, mypy config, and pytest config
- `.github/workflows/ci.yml` for automated lint, type-check, and unit-test CI
- `data/__init__.py` and `data/golden/__init__.py` to make eval data a proper package
- Backward-compatible re-export shims at the repository root for every moved module (zero breakage to legacy callers)

### Changed
- `app.py` now imports directly from canonical `astro_agent.*` paths
- All `tests/` files updated to use canonical `astro_agent.*` imports
- `astro_engine.py` updated to re-export from `astro_agent.*` sub-packages
- `data/golden/schema.py` updated to import `SUPPORTED_INTENTS` from `astro_agent.routing.intent_router`

### Deprecated
- Root-level module files (`agent_loop.py`, `chart_engine.py`, `cities.py`, etc.) are now thin shims and will be removed in a future release

---

## [0.1.0] — Initial release

- Vedic chart engine backed by Swiss Ephemeris (`pyswisseph`)
- Ollama-powered LLM inference with ReAct agentic tool-calling loop
- Hybrid BM25 + embedding RAG pipeline over BPHS Sharma Vol. 1 corpus (ChromaDB)
- Multi-turn conversation buffer with LLM-based summarisation
- Streamlit UI (`app.py`) with structured domain responses (career, health, wealth, family, general)
- Intent routing with rule-based fast path and LLM fallback
- JSONL interaction & LLM-call tracing
- Evaluation harnesses for career, template adherence, RAG faithfulness, and intent routing
