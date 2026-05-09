#!/usr/bin/env bash
# Ingest the Sharma Vol. 1 “effects of houses” chapters into Chroma.
# Prerequisites: Ollama on localhost:11434 with model nomic-embed-text (see rag_config.py).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}:${ROOT}/.pip_target:${PYTHONPATH:-}"

run_ingest () {
  local input="$1" chapter="$2"
  python3 knowledge_builder.py \
    --input "$input" \
    --book bphs --translator sharma --chapter "$chapter" \
    --verbose
}

# Previously ingested in-repo: 15, 19, 21–24. New OCR extractions:
run_ingest data/corpus/bphs_sharma/ch_13_judgement_of_houses.txt 13
run_ingest data/corpus/bphs_sharma/ch_14_effects_of_1_house.txt 14
run_ingest data/corpus/bphs_sharma/ch_16_effects_of_3_house.txt 16
run_ingest data/corpus/bphs_sharma/ch_17_effects_of_4_house.txt 17
run_ingest data/corpus/bphs_sharma/ch_18_effects_of_5_house.txt 18
run_ingest data/corpus/bphs_sharma/ch_20_effects_of_7_house.txt 20
run_ingest data/corpus/bphs_sharma/ch_25_effects_of_12_house.txt 25

echo "Done. Re-ingest a chapter after editing its .txt with: --replace-chapter"
