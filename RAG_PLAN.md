# RAG Plan & Progress Tracker

> Working doc for any agent (or human) picking up RAG work on this repo.
> Read this first; it links to source files and records the state of the
> retrieval pipeline.

---

## Status snapshot

- **Phase**: 4 v0 (retrieval-only) — **DONE**
- **Next phase**: PR2 (UI sources panel in `app.py`) — PENDING
- **Last eval**: `rag_v0_20260427_145833` (see `rag_eval_history.json`)
  - `rag_recall_at_3_gold = 0.90` (target ≥ 0.60) ✅
  - `rag_recall_at_5_silver = 0.90` (target ≥ 0.80) ✅
  - `rag_heuristic_delta = +0.30` (target > 0) ✅
- **Corpus**: 3 chapters / 44 chunks in `chroma_db/` (BPHS, Sharma translation)

If any metric drops below threshold, the smart-retention guardrail in
`evaluate_rag.py::passes_guardrails` will reject the run automatically.

---

## Architecture map (built)

| File | Role | Public entry points |
| --- | --- | --- |
| `rag_config.py` | Single source of truth: model, paths, weights, regex banks for entities + intents | `extract_entities()`, `detect_intent_tags()`, `estimate_tokens()` |
| `knowledge_builder.py` | Offline ingest CLI: OCR cleanup → verse split → tag → embed → upsert | `ingest()`, CLI |
| `rag_search.py` | Online retrieval: multi-query expansion → dense+filter → heuristic rerank | `search()`, `search_for_eval()` |
| `evaluate_rag.py` | Golden eval + smart retention | `evaluate()`, CLI |
| `data/golden/rag_eval_v0.json` | 10 hand-labeled cases (5 career, 3 health, 2 wealth) | — |
| `chroma_db/` | Persistent vector store (cosine space, 768-dim) | — |
| `rag_eval_history.json` | Accepted-runs index (max 3 records) | — |
| `rag_eval_records/` | Per-run report snapshots | — |

---

## Phase tracker

### Phase 4 v0 — Retrieval pipeline ✅ DONE

| Task | Status |
| --- | --- |
| `rag_config.py` (entity + intent banks, weights) | ✅ |
| `knowledge_builder.py` (chunker + tagger + embedder + upsert) | ✅ |
| `rag_search.py` (expand → retrieve → rerank) | ✅ |
| `evaluate_rag.py` (recall@k + heuristic_delta + retention) | ✅ |
| Ingest BPHS Sharma Ch. 23 (career, 19 chunks) | ✅ |
| Ingest BPHS Sharma Ch. 19 (health, 13 chunks) | ✅ |
| Ingest BPHS Sharma Ch. 24 (wealth, 12 chunks) | ✅ |
| 10-case golden dataset | ✅ |
| Idempotency on re-ingest verified (sha256 IDs) | ✅ |
| Acceptance thresholds met (0.90 / 0.90 / +0.30) | ✅ |

### PR1 — Wire retrieval into the LLM prompt ✅ DONE

This phase is now complete. `rag_search.search()` is consumed by generation via `build_rag_enriched_prompt()` in `astro_engine.py` when `--rag-on` is enabled.

| Task | File | Notes |
| --- | --- | --- |
| ✅ Add `--rag-on / --rag-off` CLI flag | `astro_engine.py` | Default remains `--rag-off` until stable-by-default decision |
| ✅ Call `rag_search.search()` in prompt-build path | `astro_engine.py` | Uses intent + derived chart facts in `build_rag_enriched_prompt()` |
| ✅ Inject retrieved chunks as `[ref:bphs-chN-vM]: <chunk text>` | `astro_engine.py` | `ClassicalReferences` block capped by `cfg.MAX_CONTEXT_TOKENS_TOTAL` |
| ✅ Citation instruction for exact `[ref:...]` use | `astro_engine.py` | `CitationRules` block inserted with retrieved refs |
| ✅ Post-generation strip of unknown `[ref:...]` tags | `astro_engine.py` | Applied in non-stream response path with strip stats for stream path |
| ✅ Update `evaluate_career.py` to compare `rag_enriched` mode | `evaluate_career.py` | Added behind `--rag` flag |
| ✅ README: add "Phase 4 PR1" usage | `README.md` | Added PR1 subsection under Phase 4 |

**Acceptance for PR1**: `evaluate_career.py` shows `rag_enriched_keyword_avg ≥ enriched_keyword_avg` on the existing career test set, and a manual eyeball confirms `[ref:...]` tags appear in 5/5 sampled responses with no fabricated tags.

### PR2 — UI sources panel ⏳ PENDING

| Task | File | Notes |
| --- | --- | --- |
| Show retrieved chunks in a Streamlit "Sources" expander | `app.py` | Group by `ref_id`, show similarity + matched entities |
| Click-to-expand chunk text | `app.py` | Useful for verifying citations |
| Toggle to disable RAG per-query | `app.py` | Helpful for A/B comparison |

### Backlog — quality and depth (Tier 2)

| Task | File(s) | Effort | Expected impact |
| --- | --- | --- | --- |
| Re-OCR or fix OCR typo for "debiltation" → "debilitation" in Ch. 23 v16 | corpus + `rag_config.py::_DIGNITY_TERMS` | S | +1 silver case |
| Sentence-aware splitter for chunks > 600 tokens | `knowledge_builder.py::_split_verses` post-pass | M | Recover gold case 7 |
| BM25 hybrid retrieval (dense + sparse, RRF merge) | `rag_search.py` | M | +5–15% recall on rare terms |
| Ingest Ch. 17 (2nd house — wealth/family), Ch. 22 (9th — father/fortune), Ch. 21 (8th — longevity) | corpus + `knowledge_builder.py` | S each | Broader query coverage |
| Ingest Ch. 33 (Karakatwas), Ch. 36 (Karakamsa) | corpus | S each | Yoga-related queries |
| Test retrieval with `intent_router.detect_intent()` instead of `expected_intent` | `evaluate_rag.py` | S | Validates production path |

### Backlog — production polish (Tier 3)

| Task | File(s) | Effort | Notes |
| --- | --- | --- | --- |
| LLM-as-judge faithfulness metric | `evaluate_rag.py` (post-PR2) | M | Use `llama3.2:3b` to score chunk-grounding |
| Cross-encoder reranker (replace heuristic) | `rag_search.py::_rerank` | L | Needs ~1 GB free RAM; keep heuristic as fallback |
| Embedding cache for incremental re-ingest | `knowledge_builder.py` | S | Already partially solved by sha256 ID skip |
| Multi-hop / query decomposition | `rag_search.py` | L | For "compare X vs Y" style questions |
| Move corpus to `data/corpus_processed/` with deterministic OCR pipeline script | `scripts/ocr_chapter.sh` | M | Reproducible from PDF |

---

## Last eval scoreboard (10 cases, 3 chapters)

```
case_id                                  intent   gold@3  silver@5  delta
career_strong_10th_lord                  career      ✓        ✓       0
career_rahu_with_10th_lord_in_8th        career      ✓        ✓       0
career_jupiter_aspect_karma_yogi         career      ✓        ✓       1
career_saturn_debilitated_10th           career      ✓        ✗       2   (silver miss = OCR typo "debiltation")
career_fame_through_moon_in_10th         career      ✓        ✓       0
health_diseases_from_6th_house           health      ✓        ✓       0
health_ascendant_lord_with_malefics      health      ✗        ✓      -3   (gold v6 oversize → length penalty)
health_8th_lord_in_6th_with_moon         health      ✓        ✓       3
wealth_11th_lord_in_own_or_angle         wealth      ✓        ✓       0
wealth_11th_lord_in_2nd_house            wealth      ✓        ✓       0
```

Two open cases above are documented under "Known limitations".

---

## Known limitations (don't re-litigate without need)

1. **Case 4 silver miss — OCR typo.** `bphs-ch23-v16` lost its `debilitated` entity tag because Tesseract OCR'd "debilitation" as "debiltation". Fix path: re-OCR with `tesseract -l eng --psm 4` for that page, OR add OCR variants (`debiltation`, `debiliation`) to `_DIGNITY_TERMS` in `rag_config.py`. Tracked in Tier 2 backlog.

2. **Case 7 gold miss — oversize chunk + length penalty.** `bphs-ch19-v6` is 679 tokens (over the 500 length-penalty threshold) so it gets demoted relative to similarly-relevant 390-token siblings. Silver `v7-8` IS retrieved at #1, so the LLM still sees correct context. Real fix: sentence-aware splitter for chunks > 600 tokens. Tracked in Tier 2 backlog.

3. **Cross-chapter pulls into wealth queries.** `bphs-ch23-v8-10` (career chapter) sometimes appears in top-3 for wealth questions because it discusses 11th-Lord exaltation. This is **correct behavior** — the verse genuinely is wealth-relevant — and recall@3 gold is unaffected. Do not "fix".

4. **Devanagari noise lines in OCR output.** Garbage like `aia amie um wa aM` appears between verses. We chose NOT to filter these aggressively because (a) they have no entities so the reranker ignores them, and (b) over-filtering risks dropping real content. Stay the course unless eval regresses.

---

## Decisions log (do not redo without strong reason)

| Decision | Rationale | Date |
| --- | --- | --- |
| ChromaDB local SQLite over Pinecone/Weaviate | Local-first, low-RAM, no service to manage | 2026-04-26 |
| `nomic-embed-text` over `text-embedding-3-small` etc. | Runs in Ollama, 274 MB, English-strong, 768-dim | 2026-04-26 |
| Heuristic reranker over cross-encoder | Cross-encoder needs ~1 GB; user has 16 GB shared with R1+macOS+Cursor | 2026-04-26 |
| Two-level chunking (chapter summary + verse) | Coarse and fine entry points; minimal extra storage | 2026-04-26 |
| sha256(chunk_text) as Chroma ID | Free idempotency on re-ingest; deterministic | 2026-04-26 |
| Boolean `intent_<name>` flags + pipe-bounded `entities` field | Chroma `where` syntax doesn't support list-contains; substring filtering works | 2026-04-27 |
| `keep_alive=0` on every embedding call | Evicts Nomic between calls so R1 keeps full VRAM | 2026-04-27 |
| `expected_intent` in golden cases (not detected) | Isolates retrieval testing from intent-routing failures | 2026-04-27 |
| Separate `rag_eval_history.json` (not shared with `eval_history.json`) | Different metric schemas; mixing breaks `_rank_tuple` | 2026-04-27 |
| `ENTITY_MATCH_CAP = 3` on entity-bonus | Unbounded entity bonus was demoting gold; cap saturates at +0.6 (parity with intent bonus) | 2026-04-27 |
| Verse-head regex caps at 2 digits (`\d{1,2}`) | Avoids false-matching "5000 Nishkas" etc. mid-paragraph | 2026-04-27 |
| Verse-head regex accepts `1/2` markers | Sharma translation uses Sanskrit half-verse markers (`7-8 1/2 If…`) | 2026-04-27 |
| Strip unknown `[ref:...]` tags post-generation while preserving stream UX | Keep stream UX responsive while ensuring evaluator/non-stream consumers only get validated citations | 2026-04-27 |

---

## Quick commands

### Ingest a chapter (idempotent)
```bash
source venv/bin/activate
python knowledge_builder.py \
  --input data/corpus/bphs_sharma/ch_19_effects_of_6_house.txt \
  --book bphs --translator sharma --chapter 19 \
  --verbose
```

### Run the eval (against golden v0)
```bash
python evaluate_rag.py \
  --golden data/golden/rag_eval_v0.json \
  --output rag_eval_report.json \
  --history rag_eval_history.json
```

Add `--no-retention` to skip writing to history (useful while iterating).

### Inspect what's in the index
```bash
python -c "
import chromadb, rag_config as cfg
client = chromadb.PersistentClient(path=cfg.CHROMA_PATH)
col = client.get_or_create_collection(name=cfg.CHROMA_COLLECTION, metadata={'hnsw:space':'cosine'})
print(f'Total: {col.count()}')
"
```

### Add a new chapter (full path)
1. Render PDF pages: `pdftoppm -r 300 -f START -l END "<book.pdf>" ocr_work/ch_NN/p -png`
2. OCR each: `for f in ocr_work/ch_NN/p-*.png; do tesseract "$f" "${f%.png}" -l eng; done`
3. Concat: `cat ocr_work/ch_NN/p-*.txt > data/corpus/bphs_sharma/ch_NN_<topic>.txt`
4. Eyeball the file for serious garbage.
5. `python knowledge_builder.py --input ... --chapter NN --verbose`
6. `rm -rf ocr_work/`
7. Add ≥2 golden cases targeting the new chapter to `data/golden/rag_eval_v0.json`.
8. Re-run eval; verify thresholds still met.

---

## Tunables (in `rag_config.py`)

If recall regresses, these are the first knobs to turn:

| Constant | Current | Effect of raising | Effect of lowering |
| --- | --- | --- | --- |
| `DENSE_TOP_K` | 10 | More candidates for reranker, slower | Tighter, faster, may drop gold |
| `RERANK_TOP_K` | 3 | More chunks to LLM (more context, more cost) | Less context, more focus |
| `ENTITY_WEIGHT` | 0.20 | Reranker leans more on entity overlap | More on dense similarity |
| `ENTITY_MATCH_CAP` | 3 | Long-entity-list chunks dominate again | Even tighter cap |
| `INTENT_WEIGHT` | 0.10 | Intent filter has more pull at rerank | Less |
| `LENGTH_PENALTY_PER_100` | 0.10 | Big chunks penalized harder | Big chunks compete |
| `LENGTH_PENALTY_THRESHOLD` | 500 | Only very long chunks penalized | More chunks penalized |
| `CHUNK_TARGET_TOKENS` | 400 | Larger chunks (more context per chunk) | Smaller chunks (more chunks) — only takes effect if a real splitter is added |
| `MAX_CONTEXT_TOKENS_TOTAL` | 1200 | More retrieved text into prompt (risk: overflow R1 16384 ctx) | Less context in prompt |

Re-run `evaluate_rag.py` after any tuning to verify guardrails still pass.

---

## Where to look for what

- "How does retrieval rerank?" → `rag_search.py::_rerank` (around line 208)
- "How does multi-query expansion work?" → `rag_search.py::expand_queries` (around line 99)
- "How are entities tagged?" → `rag_config.py::extract_entities` (around line 98)
- "How are intents detected per chunk?" → `rag_config.py::detect_intent_tags` (around line 175)
- "How are verses parsed?" → `knowledge_builder.py::VERSE_HEAD_RE` and `_split_verses`
- "What does the golden file look like?" → `data/golden/rag_eval_v0.json`
- "How does smart retention work?" → `evaluate_rag.py::maybe_save_result`

---

## When you finish a meaningful change

1. Run `python evaluate_rag.py` (with retention) to attempt history acceptance.
2. If accepted, the new record is appended to `rag_eval_history.json`. If rejected, fix or document why before continuing.
3. Update this file's **Status snapshot** + **Phase tracker** sections.
4. If a new decision was made, add a row to **Decisions log** with date and rationale.
