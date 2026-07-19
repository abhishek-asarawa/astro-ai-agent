# Astro AI Agent

Local Vedic astrology analysis pipeline with structured chart features, RAG over classical texts, and Ollama-based generation.

## Quick Start

```bash
source venv/bin/activate
streamlit run app.py
```

CLI chart + query (optional):

```bash
python -m astro_agent.llm.client --model qwen2.5:7b-instruct --timeout 120
```

Career / RAG / intent evals:

```bash
python evals/evaluate_career.py --eval-type career --runs 1 --model qwen2.5:7b-instruct --timeout 120 --workers 2
python evals/evaluate_rag.py
python evals/evaluate_real_world_questions.py
```

## Setup

### 1. Install Ollama and pull required models

```bash
# Install Ollama from https://ollama.com, then:
ollama pull qwen2.5:7b-instruct   # primary generation model
ollama pull llama3.2:3b            # intent classification model
ollama pull nomic-embed-text       # embedding model for RAG
```

### 2. Install Python dependencies

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. (Optional) Build the RAG corpus index

```bash
python scripts/ingest_bphs_from_full_pdf_dir.py --dir data/corpus/
```

The index is written to `chroma_db/` (gitignored). Without it the app still works but answers are ungrounded.

### 4. Configure environment (optional)

```bash
cp .env.example .env
# Edit .env to override model, timeout, and feature flags
```

## Standards & specs (for contributors and agents)

- Coding / comments / testing / config: [`docs/standards/`](docs/standards/)
- Business feature specs (no code): [`docs/specs/`](docs/specs/)
- Portable agent entrypoint: [`AGENTS.md`](AGENTS.md)
- Multi-book corpus engineering path: [`docs/CORPUS_PATH.md`](docs/CORPUS_PATH.md)

## Project Overview

Main surfaces:

- **Streamlit UI** (`app.py`): thin chat UI over `astro_agent.service.run_consultation`
- **Consultation service** (`astro_agent/service/`): chart → intent → agent/RAG/linear → humanize
- **Package** (`astro_agent/`): chart math, routing, RAG, LLM client, optional ReAct agent loop
- **Evals** (`evals/`): career, RAG, intent, real-world quality gates

## Package layout

```
astro_agent/
  chart/          # Swiss Ephemeris features, dashas, timing
  routing/        # hybrid intent detection
  intents.py      # single source of truth for intents + keyword banks
  rag/            # ingest, hybrid search, citation inject
  llm/            # Ollama client, prompts, conversation, humanizer, config
  agent/          # ReAct loop + tool registry (agent/tools/)
  service/        # run_consultation orchestration
  utils/          # cities, tracer, response parse, confidence
prompts/          # deprecated shim → astro_agent.llm.prompts
```

## Intent-Aware Routing

- Supported intents: `career`, `health`, `wealth`, `family`, `general` (see `astro_agent.intents`)
- Detection: hybrid (rules first, LLM fallback when ambiguous)
- Single-best intent per query; unclear cases fall back to `general`

## Architecture

1. **Chart** — birth details (IST) → Swiss Ephemeris → lagna/planets/lords/yogas/dashas/timing
2. **Intent** — `detect_intent` in `astro_agent.routing.intent_router`
3. **Answer path** — optional agent tools (`run_agent_loop`) or RAG-enriched / plain domain prompts via `run_consultation`
4. **Generation** — Ollama `/api/generate` (linear) or `/api/chat` (agent tools)
5. **Post-process** — citation strip, confidence calibrate, humanize for chat display

## Evaluation

- `evals/evaluate_career.py` — baseline vs enriched prompts, keyword + template scores, smart retention
- `evals/evaluate_rag.py` — retrieval gold/silver
- `evals/evaluate_real_world_questions.py` — colloquial question benchmark
- Golden data under `data/golden/`

## Commands

### Run interactive UI

Prerequisites: venv activated; Ollama running (default `http://localhost:11434`, overridable via `ASTRO_OLLAMA_HOST`).

```bash
streamlit run app.py
```

### Unit tests / lint

```bash
ASTRO_CI=1 pytest
ruff check astro_agent tests
mypy astro_agent
```
