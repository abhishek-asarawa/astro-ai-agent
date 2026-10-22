# Astro AI Agent

Local Vedic astrology analysis pipeline with structured chart features, RAG over classical texts, and Ollama-based generation.

## Quick Start

```bash
# Create .venv311 once — see Setup §2
source .venv311/bin/activate
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

CI runs Python 3.11, and the pre-push gate requires 3.11 or newer.

```bash
brew install python@3.11
/opt/homebrew/opt/python@3.11/bin/python3.11 -m venv .venv311
source .venv311/bin/activate
pip install -r requirements-dev.txt
pip install -e .
```

### 2b. Install git hooks (once per clone)

```bash
./scripts/install-hooks.sh
```

This points git at `.githooks/`: commits run the fast lint gate, pushes run the
full CI-equivalent gate (ruff, mypy, pytest), so PR checks hold no surprises.
Activate `.venv311` before commit/push so the hooks find Python 3.11 tooling.

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

- Product roadmap (milestones, decisions, next steps): [`docs/ROADMAP.md`](docs/ROADMAP.md)
- Coding / comments / testing / config: [`docs/standards/`](docs/standards/)
- Business feature specs (no code): [`docs/specs/`](docs/specs/)
- Portable agent entrypoint: [`AGENTS.md`](AGENTS.md)
- Multi-book corpus engineering path: [`docs/CORPUS_PATH.md`](docs/CORPUS_PATH.md)
- Parallel worktree Dev Containers: [`docs/development/devcontainers.md`](docs/development/devcontainers.md)

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

Prerequisites: `.venv311` activated; Ollama running (default `http://localhost:11434`, overridable via `ASTRO_OLLAMA_HOST`).

```bash
streamlit run app.py
```

### Quality gate

Local hooks and GitHub Actions run the same script:

```bash
./scripts/run_ci_checks.sh fast   # ruff lint + format check (pre-commit)
./scripts/run_ci_checks.sh full   # + mypy + ASTRO_CI=1 pytest (pre-push, CI)
```

Bypass only in emergencies with `git push --no-verify`; CI will still fail.
