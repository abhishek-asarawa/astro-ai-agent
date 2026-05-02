# Astro AI Agent

Local Vedic astrology analysis pipeline with structured chart features and Ollama-based prediction/evaluation.

## Quick Start

```bash
source venv/bin/activate
```

```bash
python astro_engine.py --model deepseek-r1:7b --timeout 120
```

```bash
python evaluate_career.py --eval-type career --runs 1 --model deepseek-r1:7b --timeout 120 --workers 2 --output career_eval_report.json --history eval_history.json
```

```bash
streamlit run app.py
```

## Project Overview

This project has two main flows:

- `astro_engine.py`: builds chart features and runs a career prediction query on a local Ollama model.
- `evaluate_career.py`: runs benchmark evaluations (baseline vs enriched prompts), scores outputs, and applies smart retention for historical best results.

## Intent-Aware Routing

The Streamlit app now detects user intent from the question and routes to one domain prompt.

- Supported intents: `career`, `health`, `wealth`, `family`, `general`
- Detection strategy: hybrid (`rule-based` first, `LLM fallback` when ambiguous)
- Multi-intent behavior: single-best intent is selected (one domain response per query)
- Fallback safety: if detection/classification is unclear, app falls back to `general`

## Architecture

### 1) Chart + Prompt Pipeline (`astro_engine.py`)

- Input: birth details in IST (`year`, `month`, `day`, `hour`, `minute`, `city`)
- Time conversion: `convert_ist_to_utc` from `utils.py`
- Astronomical computation: Swiss Ephemeris (`swisseph`)
- Feature mapping:
  - `mapper.py`: rashi/nakshatra mapping
  - `lords.py`: house lordships
  - `yogas.py`: planetary dignity tags
  - `dashas.py`: Vimshottari dasha timeline
- Prompt assembly: structured, career-focused format
- Inference: Ollama generate API

### 2) Evaluation Pipeline (`evaluate_career.py`)

- Runs two prompt modes for each test case:
  - `baseline`
  - `enriched`
- Executes jobs in parallel (`--workers`)
- Scores:
  - `keyword_score` (expected keyword coverage)
  - `template_score` (format adherence for enriched responses)
- Summary metrics:
  - `baseline_keyword_avg`
  - `enriched_keyword_avg`
  - `enriched_template_avg`
  - `delta_keyword_avg`

### 3) Smart Result Retention

Evaluation history is persisted with a quality gate:

1. If no past history: save result.
2. If past history exists: save only when guardrails pass:
   - new `enriched_keyword_avg` is higher than best historical record
   - new `enriched_template_avg` is not lower than the best historical record
3. Keep at most 3 accepted history records.
4. If full and a new accepted record arrives:
   - identify least-good records
   - evict the **oldest** among those least-good records

History is global (all eval types/models compared together).

## Files

- `astro_engine.py`: chart feature builder and Ollama query runtime
- `evaluate_career.py`: evaluator, scoring, retention, and history logic
- `eval_history.json`: accepted history index (created after accepted runs)
- `eval_records/`: accepted report snapshots (created after accepted runs)
- `career_eval_report.json`: latest run output file (default)

## Setup

Use project venv Python:

```bash
source venv/bin/activate
```

## Commands

### Run interactive UI (Streamlit)

Prerequisites:

- Activate venv (`source venv/bin/activate`)
- Ensure Ollama is running locally on `http://localhost:11434`

Launch:

```bash
streamlit run app.py
```

Typical UI flow:

1. Set birth date, birth time, and city.
2. Enter what you are looking for in the question box.
3. (Optional) Override model and timeout.
4. Click `Generate Analysis` to view model output, dasha snapshot, chart details, and detected intent metadata.

### Run one prediction

```bash
python astro_engine.py \
  --year 1998 --month 9 --day 27 --hour 13 --minute 0 --city delhi \
  --question "What is the professional outlook for this chart?" \
  --model deepseek-r1:7b \
  --timeout 120
```

Optional:

- `--no-preview` to skip prompt preview.

### Run evaluation (single quick pass)

```bash
python evaluate_career.py \
  --eval-type career \
  --runs 1 \
  --model deepseek-r1:7b \
  --timeout 120 \
  --workers 2 \
  --output career_eval_report.json \
  --history eval_history.json
```

### Run intent detection evaluation

```bash
python evaluate_intent_detection.py \
  --model deepseek-r1:7b \
  --timeout 120 \
  --output intent_detection_eval_report.json
```

### Run intent routing evaluation (end-to-end)

```bash
python evaluate_intent_routing.py \
  --model deepseek-r1:7b \
  --timeout 120 \
  --workers 2 \
  --output intent_routing_eval_report.json
```

### Stable benchmark run (recommended)

```bash
python evaluate_career.py \
  --eval-type career \
  --runs 3 \
  --model deepseek-r1:7b \
  --timeout 600 \
  --workers 2 \
  --output career_eval_report.json \
  --history eval_history.json
```

## Configuration

CLI overrides environment variables. Priority: **CLI > env > defaults**.

Supported env vars:

- `ASTRO_MODEL_NAME`
- `ASTRO_OLLAMA_TIMEOUT_S`

Example:

```bash
export ASTRO_MODEL_NAME=deepseek-r1:7b
export ASTRO_OLLAMA_TIMEOUT_S=240
python evaluate_career.py --runs 2 --workers 2
```

## Output Interpretation

Read `summary` in `career_eval_report.json`:

- `delta_keyword_avg > 0`: enriched prompt beats baseline on keyword metric
- `enriched_template_avg` close to `1.0`: model follows required response format well

Also check `save_decision` to see whether this run was accepted into history.

## Phase 4: RAG v0 (Classical Text Retrieval)

A local-first RAG layer that grounds answers in classical Vedic astrology
texts (BPHS, Sharma translation) with verifiable `[ref:...]` citations.
Optimized for an M1 Pro 16 GB budget: heuristic reranker (no cross-encoder),
`nomic-embed-text` embeddings via Ollama with `keep_alive=0` so the embedding
model is evicted between calls, and ChromaDB on local SQLite.

### Components

- `rag_config.py` — single source of truth for embed model, Chroma path,
  chunking targets, reranker weights, and entity / intent regex banks.
- `knowledge_builder.py` — idempotent ingest CLI: cleans OCR artifacts,
  splits a chapter into verse-level chunks (+ one chapter-summary chunk),
  tags entities and intents, embeds, and upserts. SHA-256 chunk IDs make
  re-runs free.
- `rag_search.py` — multi-query expansion (literal question + structural
  chart query + intent-keyword query), intent-filtered Chroma dense search,
  merge / dedupe by ref_id, heuristic rerank.
- `evaluate_rag.py` — runs the golden dataset through the retriever and
  scores `rag_recall_at_3_gold`, `rag_recall_at_5_silver`, and
  `rag_heuristic_delta` (mean rank-up of gold refs after rerank). Smart
  retention into `rag_eval_history.json`.

### Chunk schema (Chroma metadata)

```
book              "bphs"
translator        "sharma"
chapter           23
verse_start       2
verse_end         2          // == verse_start for single verses; >start for blocks
chunk_level       "verse" | "chapter"
ref_id            "bphs-ch23-v2" | "bphs-ch23-v8-10" | "bphs-ch23-summary"
entities          "|10th_lord|exaltation|own_sign|"   // |-bounded for safe substring
token_count       317
intent_career     true
intent_wealth     false
intent_health     false
intent_family     false
intent_general    true       // true if any specific intent fires
```

Chunk IDs are `sha256(text)` so the same text never re-embeds.

### Pre-flight

```bash
ollama pull nomic-embed-text
# (Optional, recommended) hint Ollama to share VRAM with DeepSeek-R1:
launchctl setenv OLLAMA_MAX_LOADED_MODELS 2
launchctl setenv OLLAMA_NUM_PARALLEL 1
```

### Ingest a chapter

```bash
python knowledge_builder.py \
  --input data/corpus/bphs_sharma/ch_23_effects_of_10_house.txt \
  --book bphs --translator sharma --chapter 23 \
  --verbose
```

Output: `Ingested N new chunks, skipped M already present.` Re-running with
the same input is a no-op.

### Evaluate retrieval

```bash
python evaluate_rag.py \
  --golden data/golden/rag_eval_v0.json \
  --output rag_eval_report.json \
  --history rag_eval_history.json
```

Acceptance thresholds for v0 (single-chapter corpus, 5 golden cases):

- `rag_recall_at_3_gold >= 0.6` (≥3 of 5 gold refs surface in the post-rerank top-3)
- `rag_recall_at_5_silver >= 0.8`
- `rag_heuristic_delta > 0` (the heuristic reranker is doing useful work)

Smart retention (mirrors `evaluate_career.py`):

1. New record accepted only if `rag_recall_at_3_gold` strictly improves and
   `rag_recall_at_5_silver` does not drop vs the current best.
2. Up to 3 records kept; oldest of the least-good is evicted on overflow.
3. Accepted reports are snapshotted under `rag_eval_records/`.

### Phase 4 PR1: RAG-enriched generation

PR1 wires retrieval into generation so outputs can cite classical BPHS chunks
using verified `[ref:...]` tags.

Enable RAG in CLI:

```bash
python astro_engine.py \
  --question "What is the professional outlook for this chart?" \
  --rag-on
```

Compare baseline/enriched/rag_enriched in evaluator:

```bash
python evaluate_career.py --rag --runs 2
```

What changes in prompts:

- A `ClassicalReferences:` block is injected before `Question:`.
- References are inserted as `[ref:<ref_id>]: <chunk text>`.
- A `CitationRules:` block instructs the model to use only provided tags.

Reference validation:

- Non-streaming calls (`query_ollama_once`) strip unknown fabricated `[ref:...]`
  tags post-generation.
- Streaming CLI keeps live token UX and prints a footer with stripped tag stats.

PR1 acceptance target:

- `rag_enriched_keyword_avg >= enriched_keyword_avg`
- In 5/5 sampled outputs, at least one valid `[ref:...]` appears and fabricated
  tags are stripped.

## Notes

- `NotOpenSSLWarning` from `urllib3` can appear on macOS with LibreSSL; it is usually a warning, not a functional failure.
- Large models and high worker counts can cause slow or empty responses. Reduce `--workers` or increase `--timeout` if needed.
- The corpus directory (`data/corpus/`) and the Chroma store (`chroma_db/`)
  are gitignored. Re-run `knowledge_builder.py` after a fresh checkout.
