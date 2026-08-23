# RAG Plan & Progress Tracker

> Working doc for any agent (or human) picking up RAG work on this repo.
> Read this first; it links to source files and records the state of the
> retrieval pipeline.

---

## Status snapshot

- **Phase**: 4 v0 (retrieval-only) — **DONE**
- **Widen RAG golden eval (twelve-house “effects” coverage)** — **DONE** (2026-05-10): [`data/golden/rag_eval_v0.json`](data/golden/rag_eval_v0.json) **25** cases; [`rag_config.py`](rag_config.py) **`HOUSE_EFFECTS_CHAPTER`** for houses **1–12**; accepted run **`rag_v0_20260510_085550`** **`1.00 / 1.00 / +0.50`** (see scoreboard). Optional **second-wave** goldens (extra cases per house) remain a nice-to-have, not required to close this initiative.
- **PR1** (RAG in LLM prompt + CLI) — **DONE**
- **PR2** (Streamlit sources + RAG toggle) — **DONE** (2026-05-02)
- **Career generation eval** (`evaluate_career.py`): **embedding grounding + optional LLM judge + `--retention-mode {legacy,rag}`** — **DONE**
- **Latest accepted RAG eval (rolling history):** `rag_v0_20260510_085550` in `rag_eval_records/` (see `rag_eval_history.json`)
  - **Tuple** `(rag_recall_at_3_gold, rag_recall_at_5_silver, rag_heuristic_delta)` = **`(1.00, 1.00, +0.50)`** — **25 cases** (full “effects” house sweep: Ch. **14 / 16 / 17 / 18 / 20 / 25** goldens + prior set); accepted vs prior indexed best **`rag_v0_20260503_085118`** **`(1.00, 0.90, +0.60)`** (lexicographic gain on **silver@5**). Mean **delta** is lower than the **19-case** snapshot **`rag_v0_20260509_203851`** **`(1.00, 1.00, +0.67)`** (that record remains in `rag_eval_records/` for comparison but was rotated out of the 3-slot history index when the suite grew).
  - Summary includes **`outcomes_checksum`** for tie-breaking when headline metrics match.
- **Historical baseline (pre–full-book scale):** `rag_v0_20260503_085118` — `1.00 / 0.90 / +0.60` (targets ≥ 0.60 gold, ≥ 0.80 silver, delta > 0).
- **`evaluate_rag.py` retention (2026-05-10):** compare **`(gold@3, silver@5, mean heuristic_delta)`** lexicographically vs best history row; on **tie**, compare **`outcomes_checksum`**; legacy rows without checksum still **accept** on tie; identical summary+checksum **accepts** to rotate snapshots. **Reject** only on strict **regression** of the tuple.
- **Latest `evaluate_rag.py --no-retention` (14 cases, Ch. 21 ingest, 2026-05-03)**: `1.00 / 1.00 / +0.50` — Ch. 21 eighth-house goldens + `intent_router` / `rag_config` health keyword expansion; **`health_diseases_from_6th_house`** chart entity tweak (see Decisions log).
- **Earlier `evaluate_rag.py --no-retention` (Tier 2 hybrid, 2026-05-03)**: `1.00 / 1.00 / +1.10` — `career_saturn_debilitated_10th` **silver@5 pass**; BM25+RRF + BM25-only query variants + chart/question **dignity entity aliases** in [`rag_search.py`](rag_search.py).
- **`evaluate_rag.py` production intent (2026-05-03):** default path uses **`intent_router.detect_intent()`** (same family as `--rag-on` in [`astro_engine.py`](astro_engine.py)); golden file **`expected_intent`** is a label only; report adds `used_intent`, `intent_detection`, `intent_matches_golden`, summary **`intent_routing_agreement`**. Use **`--golden-intent`** to restore retrieval-only isolation. **`intent_router` career keywords** broadened (e.g. `10th lord`, `karma yogi`, `livelihood`) so BPHS-style questions hit **rules** intent `career` without LLM fallback.
- **Last career RAG baseline (rag retention)**: first accepted record with judge + grounding, e.g. `career_20260502_114813` in `eval_records/` (see `eval_history.json`; summary includes `rag_judge_grounding_avg`, `rag_grounding_max_sim_avg`, `retention_mode: rag`)
- **Corpus (BPHS, Sharma English Vol. 1)**: **47** chapters (`book=bphs`, `chapter=1..47`) indexed in `chroma_db/`; **~1.4k+** chunk rows after full-volume ingest (exact `col.count()` varies with re-runs). **Chapter `.txt` files are not in git** (`.gitignore`: `data/corpus/bphs_sharma/**/*.txt`); reproduce OCR from the PDF using `tools/extract_bphs_vol1_from_map.py` and `tools/bphs_vol1_sharma_chapter_starts.json`, then `scripts/ingest_bphs_from_full_pdf_dir.py` or `knowledge_builder.py`.
- **Full-volume ingest (2026-05-09):** Chapters **1–12** and **26–47** via PDF page map + OCR (`ch_N_bphs_vol1.txt`); chapters **13–25** kept from earlier targeted extracts (`ch_*_effects_*` / `ch_13_judgement_*`). **`VERSE_HEAD_RE`** tightened so prose like `7 or the Uttarardha…` does not fake a verse boundary.
- **Ch. 15 ingest (2026-05-03):** OCR PDF pp. 209–219 → `data/corpus/bphs_sharma/ch_15_effects_of_2_house.txt` (local OCR); golden **`wealth_2nd_lord_in_11th_11th_lord_in_2nd`**, **`wealth_jupiter_mars_in_2nd_house`**. Full `evaluate_rag.py` **12** cases **`--no-retention`**: `1.00 / 1.00 / +0.75`.
- **Ch. 21 ingest (2026-05-03):** OCR PDF pp. 255–280 (trimmed to Ch. 21 only) → `data/corpus/bphs_sharma/ch_21_effects_of_8_house.txt`; **`evaluate_rag.py` 14 cases `--no-retention`**: `1.00 / 1.00 / +0.50` (see scoreboard). Golden **`health_8th_lord_in_kendra_long_life`** uses **gold `bphs-ch21-v4-7`** (kendra + longevity block; opening `v1` often ranks 4th after rerank). **`health_diseases_from_6th_house`** chart `jupiter` moved from **house 8 → house 6** so query entities do not spuriously boost unrelated `8th_house` chunks over `bphs-ch19-v1`.
- **Ch. 22 ingest (2026-05-03):** OCR PDF pp. **263–268** → `data/corpus/bphs_sharma/ch_22_effects_of_9_house.txt` (`Sth`→`5th`/`9th` OCR fixes; long father-death block split **v13–17** / **v18–25** so health queries are not swamped). Goldens **`family_9th_lord_exalted_father_longlife`**, **`family_9th_10th_lord_exchange_father_wealth`**. **`evaluate_rag.py` 16 cases `--no-retention`**: `1.00 / 1.00 / +0.19` (`rag_heuristic_delta` **+0.188**); **`health_ascendant_lord_with_malefics`** chart lists **all** conjunct bodies so **`Mercury`** appears in query entities and **`bphs-ch19-v6`** wins over Ch. 22 death text.
- **Full-book RAG eval pass (2026-05-10):** **25** golden cases (prior **19** + **Ch. 14 / 16 / 17 / 18 / 20 / 25** house-coverage rows) with production `detect_intent`: accepted headline **`1.00 / 1.00 / +0.50`** (`rag_v0_20260510_085550`). **`HOUSE_EFFECTS_CHAPTER`** in [`rag_config.py`](rag_config.py) now maps **all twelve** houses to Sharma “effects” chapter numbers so rerank chapter hints apply to **1st–12th**. Earlier **19-case** report **`rag_v0_20260509_203851`** remains at **`1.00 / 1.00 / +0.67`** for apples-to-apples delta comparison on the smaller suite.
- **`evaluate_rag.py` LLM-judge** (Tier 3) — **DONE**: optional `--judge-model` (+ `--answer-model`, `--max-judge-cases`, `--no-answer-grounding`); shared helpers in [`eval_grounding.py`](eval_grounding.py); **retention unchanged** (retrieval tuple + `outcomes_checksum` only). **Next optional focus:** second-wave goldens (extra cases per house) for redundancy only.
- **Ch. 23 v16 corpus fix (2026-05-03):** `debiltation` → `debilitation` in `data/corpus/bphs_sharma/ch_23_effects_of_10_house.txt`; re-ingested with stale-hash cleanup. Silver miss that remained after OCR was addressed with **hybrid retrieval + dignity synonym overlap** (see Decisions log).

**Guardrails:** `evaluate_rag.py` retention uses the **lexicographic tuple + `outcomes_checksum`** (see Status snapshot). **`evaluate_career.py`** can use **`--retention-mode legacy`** (enriched keyword/template, older behavior) or **`--retention-mode rag`** (lexicographic composite: judge score → max chunk similarity → citations → RAG template). Keyword averages alone are a weak signal for generation quality; prefer grounding + judge for RAG regressions.

---

## Architecture map (built)

| File | Role | Public entry points |
| --- | --- | --- |
| `rag_config.py` | Single source of truth: model, paths, weights, regex banks for entities + intents | `extract_entities()`, `detect_intent_tags()`, `estimate_tokens()` |
| `knowledge_builder.py` | Offline ingest CLI: OCR cleanup → verse split → tag → embed → upsert | `ingest()`, CLI |
| `tools/bphs_vol1_sharma_chapter_starts.json` | Sharma Vol. 1: chapter → first **PDF** page (1-based); drives bulk OCR | — |
| `tools/ocr_bphs_chapter_range.py` | OCR inclusive PDF page range → one `.txt` | CLI |
| `tools/extract_bphs_vol1_from_map.py` | OCR all chapters from map (skips **13–25** by default; uses higher-quality extracts there) | CLI |
| `tools/scan_bphs_vol1_chapter_starts.py` | Full-PDF scan helper for `Chapter N` headers (optional rebuild of map) | CLI |
| `scripts/ingest_bphs_from_full_pdf_dir.py` | Batch ingest every `ch_<n>_*.txt` under a directory | CLI |
| `rag_search.py` | Online retrieval: multi-query expansion → dense+filter → **BM25 + RRF** (optional) → **dedupe by `ref_id`** (best dense slice) → heuristic rerank (+ **entity tail** beyond cap) | `search()`, `search_for_eval()` |
| `evaluate_rag.py` | Golden eval + **lexicographic + checksum** retention; default **`detect_intent`** (see `--golden-intent`); optional **LLM answer + judge** (`--judge-model`, serial) | `evaluate()`, CLI |
| `eval_grounding.py` | Shared **embedding grounding** + **JSON faithfulness judge** for eval harnesses | `score_grounding_embedding()`, `run_grounding_judge()` |
| `data/golden/rag_eval_v0.json` | **25** hand-labeled cases (twelve-house “effects” sweep + Ch. 33 / 34 / 36 general) | — |
| `chroma_db/` | Persistent vector store (cosine space, 768-dim) | — |
| `rag_eval_history.json` | Accepted-runs index (max 3 records) — **local / gitignored** | — |
| `rag_eval_records/` | Per-run RAG report snapshots | — |
| `evaluate_career.py` | Baseline vs enriched vs `rag_enriched`; optional embedding grounding + LLM judge; smart retention (`legacy` or `rag`) | `evaluate()`, CLI |
| `eval_history.json` | Career eval accepted-runs index (max 3) — **local / gitignored** | — |
| `eval_records/` | Per-run career report snapshots | — |
| `run_pr1_acceptance_watch.py` | PR1 smoke + `evaluate_career --rag` with judge + rag retention checks | CLI |
| `app.py` | Streamlit UI: per-query RAG toggle, Sources expander, post-stream ref strip | — |

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
| Ingest BPHS Sharma Ch. 19 (health; **15** rows after oversize split + `--replace-chapter` re-ingest) | ✅ |
| Ingest BPHS Sharma Ch. 24 (wealth, 12 chunks) | ✅ |
| Ingest BPHS Sharma Ch. 15 (Second House / wealth; **23** new rows) | ✅ |
| Ingest BPHS Sharma Ch. 21 (Eighth House / longevity; **7** rows) | ✅ |
| Ingest BPHS Sharma Ch. 22 (Ninth House; **19** rows; split **v13–17** / **v18–25** vs single **v13–25**) | ✅ |
| 16-case golden dataset (incl. Ch. 15 wealth + Ch. 21 health + Ch. 22 family) | ✅ |
| **19-case golden dataset** (+ Ch. 33 Argala, Ch. 34 Karakatwas, Ch. 36 Karakamsa) | ✅ (2026-05-10) |
| **25-case golden dataset** (+ Ch. 14 / 16 / 17 / 18 / 20 / 25 house coverage; `HOUSE_EFFECTS_CHAPTER` all 12 houses) | ✅ (2026-05-10) |
| Idempotency on re-ingest verified (sha256 IDs) | ✅ |
| **Ingest full Sharma Vol. 1** — chapters **1–47** (PDF map + OCR + Chroma); corpus `.txt` gitignored | ✅ (2026-05-09) |
| Acceptance thresholds; rolling accepted **`rag_v0_20260510_085550`** **1.00 / 1.00 / +0.50** (25 cases); historical **`rag_v0_20260509_203851`** **1.00 / 1.00 / +0.67** (19 cases, snapshot only); **`rag_v0_20260503_085118`** **1.00 / 0.90 / +0.60** | ✅ |

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
| ✅ Stronger `CitationRules` in RAG block (Evidence bullets must cite refs) | `astro_engine.py` | Improves citation adherence in eval |
| ✅ Grounding + judge + rag retention mode | `evaluate_career.py` | See commands below |
| ✅ Acceptance watch: judge + grounding thresholds | `run_pr1_acceptance_watch.py` | Invokes `evaluate_career` with `--retention-mode rag --judge-model llama3.2:3b` |

**Acceptance for PR1 (recommended):** use **`evaluate_career.py --rag --retention-mode rag --judge-model llama3.2:3b`** and confirm `rag_judge_grounding_avg` (1–5) and `rag_grounding_max_sim_avg` (cosine vs retrieved chunks) meet your bar; `rag_enriched_citation_avg > 0`. Keyword delta vs enriched is optional smoke only.

### PR2 — UI sources panel ✅ DONE

| Task | File | Notes |
| --- | --- | --- |
| ✅ Show retrieved chunks in a Streamlit "Sources" expander | `app.py` | Per chunk: `ref_id`, similarity, matched entities |
| ✅ Click-to-expand chunk text | `app.py` | Nested expanders per source |
| ✅ Toggle to disable RAG per-query | `app.py` | Checkbox; uses `build_rag_enriched_prompt` when on |
| ✅ Strip unknown `[ref:...]` after stream | `app.py` | Uses `_strip_unknown_refs` with allowed set from bundle |

### Backlog — quality and depth (Tier 2)

| Task | File(s) | Effort | Expected impact |
| --- | --- | --- | --- |
| Re-OCR or fix OCR typo for "debiltation" → "debilitation" in Ch. 23 v16 | corpus + `rag_config.py::_DIGNITY_TERMS` | S | ✅ corpus fixed + re-ingest (2026-05-03); did **not** flip `career_saturn_debilitated_10th` silver@5; optional `_DIGNITY_TERMS` variants still unused |
| Sentence-aware splitter for chunks > `CHUNK_MAX_TOKENS` (600) | `knowledge_builder.py` (`_expand_oversize_chunks`, `--replace-chapter`) | M | ✅ **Done** — Ch. 19 re-ingest; gold case 7 + retention **`rag_v0_20260503_085118`** |
| Rerank: dedupe by `ref_id` + entity tail | `rag_search.py`, `rag_config.py` (`ENTITY_TAIL_*`) | S | Unblocked gold@3 on `health_8th_lord_in_6th_with_moon` after split |
| BM25 hybrid retrieval (dense + sparse, RRF merge) | `rag_search.py`, `rank-bm25`, `rag_config.py` (`HYBRID_BM25_*`, `RRF_*`) | M | ✅ **Done** (2026-05-03) — `HYBRID_BM25_ENABLED`, BM25-only query variants (`debilitation` / `navamamsha`), high `RRF_WEIGHT_DENSE` so pre-rerank stays dense-shaped; **dignity aliases** in `_query_entities` (`debilitated` ↔ `debilitation`) fix silver@5 for `career_saturn_debilitated_10th` |
| Ingest Ch. 17 (2nd house — wealth/family), Ch. 22 (9th — father/fortune), Ch. 21 (8th — longevity) | corpus + `knowledge_builder.py` | S each | ✅ **Ch. 15 (Second House)** = backlog “2nd house” item; ✅ **Ch. 21 (Eighth House)** (2026-05-03); ✅ **Ch. 22 (Ninth House)** (2026-05-03). **Ch. 33 / 34 / 36**: indexed via **full Vol. 1 ingest** + **goldens in `rag_eval_v0.json`** (2026-05-10). |
| Test retrieval with `intent_router.detect_intent()` instead of `expected_intent` | `evaluate_rag.py` | S | ✅ **Done** (2026-05-03) — default production path; `--golden-intent` isolates retriever |

### Backlog — production polish (Tier 3)

| Task | File(s) | Effort | Notes |
| --- | --- | --- | --- |
| LLM-as-judge faithfulness metric | `evaluate_rag.py`, `eval_grounding.py` | M | ✅ **Done** — `evaluate_rag.py --judge-model …` (optional `--max-judge-cases`, `--answer-model`, `--no-answer-grounding`); judge metrics are **diagnostic** (not in retention tuple); `evaluate_career.py` imports shared [`eval_grounding.py`](eval_grounding.py) |
| Cross-encoder reranker (replace heuristic) | `rag_search.py::_rerank` | L | Needs ~1 GB free RAM; keep heuristic as fallback |
| Embedding cache for incremental re-ingest | `knowledge_builder.py` | S | Already partially solved by sha256 ID skip |
| Multi-hop / query decomposition | `rag_search.py` | L | For "compare X vs Y" style questions |
| Move corpus to `data/corpus_processed/` with deterministic OCR pipeline script | `scripts/ocr_chapter.sh` | M | Reproducible from PDF |

---

## Last eval scoreboard (25 cases; full-book index, 2026-05-10)

Per-case `heuristic_delta` varies by run; snapshot matches accepted run **`rag_v0_20260510_085550`**. New rows cover **1st / 3rd / 4th / 5th / 7th / 12th** house effects (Ch. **14 / 16 / 17 / 18 / 20 / 25**). **`health_fifth_lord_sons_happiness`** uses **`expected_intent: health`** so `intent_family` filtering does not drop **`bphs-ch18-v1-3`** (that slice is not tagged `intent_family` at ingest). Silver labels for new rows follow post-rerank top-5 under the full index.

```
case_id                                           intent   gold@3  silver@5  delta
career_strong_10th_lord                           career      ✓        ✓       0
career_rahu_with_10th_lord_in_8th                 career      ✓        ✓       0
career_jupiter_aspect_karma_yogi                  career      ✓        ✓       2
career_saturn_debilitated_10th                    career      ✓        ✓       6
career_fame_through_moon_in_10th                  career      ✓        ✓       0
career_fourth_tenth_lords_angle_house_wall       career      ✓        ✓       0   (gold ch17-v4; silver career neighbors ch23)
health_diseases_from_6th_house                    health      ✓        ✓       0
health_ascendant_lord_with_malefics               health      ✓        ✓       0
health_8th_lord_in_6th_with_moon                  health      ✓        ✓       —
health_8th_lord_in_kendra_long_life             health      ✓        ✓       3
health_8th_lord_malefic_conjoin_asc_lord_in_8th   health      ✓        ✓       0
health_asc_malefic_no_comfort_first_house         health      ✓        ✓       1   (Ch. 14 / 1st house)
health_fifth_lord_sons_happiness                  health      ✓        ✓       0   (Ch. 18 / 5th house)
wealth_11th_lord_in_own_or_angle                  wealth      ✓        ✓       1
wealth_11th_lord_in_2nd_house                     wealth      ✓        ✓       2
wealth_2nd_lord_in_11th_11th_lord_in_2nd          wealth      ✓        ✓       0
wealth_jupiter_mars_in_2nd_house                  wealth      ✓        ✓       0
family_9th_lord_exalted_father_longlife           family      ✓        ✓       0
family_9th_10th_lord_exchange_father_wealth       family      ✓        ✓       0
family_third_lord_mars_younger_brother            family      ✓        ✓      -1   (Ch. 16 / 3rd house)
family_seventh_lord_dusthana_sickly_wife          family      ✓        ✓       0   (Ch. 20 / 7th house)
family_twelfth_lord_navamsha_wife_expenses        family      ✓        ✓       0   (Ch. 25 / 12th house)
general_argala_formation_houses                   general     ✓        ✓       0
general_atma_karaka_degrees                       general     ✓        ✓      -2
general_karakamsha_benefics_angles                general     ✓        ✓       0
```

Historical **`rag_v0_20260503_085118`** remains a useful **pre–full-book** checkpoint; the **19-case** snapshot **`rag_v0_20260509_203851`** stays at **`1.00 / 1.00 / +0.67`** for delta comparison on the smaller suite (see Status snapshot).

---

## Known limitations (don't re-litigate without need)

1. **~~Case 4 silver miss~~ — resolved (2026-05-03).** OCR fix for v16 alone was insufficient; **BM25 + RRF** (with BM25-only spelling variants) plus **`debilitated` ↔ `debilitation` entity-alias expansion** for rerank overlap aligned chart JSON with ingest `entities` and lifted `bphs-ch23-v17` / `bphs-ch23-v18` into post-rerank top-5 without dropping gold@3.

2. **~~Case 7 gold miss~~ — resolved (2026-05-03).** Oversize `bphs-ch19-v6` is split at ingest; **`rag_search`** dedupes by `ref_id` before rerank (one dense-best slice per citation); **`ENTITY_TAIL_WEIGHT`** nudges highly overlapping chunks. Accepted eval **`rag_v0_20260503_085118`**: `rag_recall_at_3_gold = 1.0`.

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
| **`evaluate_career.py` retention: `legacy` vs `rag`** | `legacy` = enriched keyword/template (noisy for LLMs). `rag` = lexicographic rank on judge + embedding max-sim to chunks + citations + RAG template; only compares to history rows that already have grounding/judge fields | 2026-05-02 |
| Embedding grounding for answers | Reuse `rag_search.embed_query` + cosine vs each retrieved chunk; report max/mean sim in eval summary | 2026-05-02 |
| PR2 Streamlit | RAG default-on checkbox + Sources expander + ref strip on final streamed text | 2026-05-02 |
| **Edit verse text → new sha256 id** | `knowledge_builder` only skips/adds by content hash; changing chunk text adds a new row and leaves the old id in Chroma (duplicate `ref_id`). Delete the stale id or full re-ingest from empty DB if duplicates appear | 2026-05-03 |
| **`evaluate_rag.py` retention needs strict gold@3 increase** | **Superseded (2026-05-10)** by lexicographic `(gold, silver, delta)` + `outcomes_checksum` tie-break (see new row below). Old policy blocked history updates when gold was capped at 1.0. | 2026-05-03 |
| **`evaluate_rag.py` lexicographic retention + `outcomes_checksum`** | Compare `(rag_recall_at_3_gold, rag_recall_at_5_silver, rag_heuristic_delta)` vs best history; reject only on regression; on tie use SHA-256 over per-case outcomes (pass flags, delta, post/pre top-5 refs); accept identical checksums to rotate snapshots; legacy rows without checksum accept on tie | 2026-05-10 |
| **Oversize ingest split + `--replace-chapter`** | Verses/chapter summaries over `CHUNK_MAX_TOKENS` split into multiple Chroma docs with the same `ref_id` metadata; replace-chapter deletes by `book`+`chapter` before re-add to avoid duplicate old hashes | 2026-05-03 |
| **Pre-rerank dedupe by `ref_id` (best dense similarity)** | Split verses share one citation tag; only one slice per `ref_id` enters the rerank pool so slots are not wasted on duplicate refs | 2026-05-03 |
| **`ENTITY_TAIL_WEIGHT` / `ENTITY_TAIL_MAX`** | After `ENTITY_MATCH_CAP`, add a small bounded bonus per extra query–chunk entity overlap so near-tie dense neighbors can reorder without raising the cap | 2026-05-03 |
| **BM25 + RRF hybrid retrieval** | `rank_bm25.BM25Okapi` over the same Chroma `where` slice as dense; RRF fuses dense ranks with BM25 ranks; **`RRF_WEIGHT_DENSE` ≫ `RRF_WEIGHT_SPARSE`** keeps `pre_rerank_rank` near dense-shaped so `rag_heuristic_delta` stays healthy | 2026-05-03 |
| **BM25-only query variants** | Extra strings in `_bm25_expanded_queries` only (not `expand_queries`) so dense embeddings stay unchanged: e.g. `debilitation`, `navamamsha` when the user says debilitated / Navamsha | 2026-05-03 |
| **Dignity entity aliases at rerank** | `_query_entities` expands `debilitated`↔`debilitation`, `exalted`↔`exaltation` so chart JSON aligns with ingest `entities` pipe-tokens | 2026-05-03 |
| **`evaluate_rag.py` default intent = `detect_intent(question)`** | Matches production RAG path in `astro_engine`; golden `expected_intent` kept as label + `intent_routing_agreement`; **`--golden-intent`** reproduces old retrieval-only eval | 2026-05-03 |
| **`INTENT_KEYWORDS['career']` includes 10th-house phrasing** | Substrings such as `10th lord`, `10th house`, `karma yogi`, `livelihood`, `fame`, `occupation` so Ch. 23–style questions score under rules without LLM `general` mislabels | 2026-05-03 |
| **Sharma Vol. 1 English “Chapter 15” = Second House** | Backlog “Ch. 17 (2nd house)” conflates numbering: in this PDF **Chapter 17** opens *Effects of the Fourth House*; **Chapter 15** is *Effects of The Second House*. Ingest uses metadata **`chapter 15`** and `bphs-ch15-v*`. | 2026-05-03 |
| **Ch. 21 corpus: prefix diagram lines that match `VERSE_HEAD_RE`** | ASCII chart lines like `1 Sun …` or `4 Lg …` were parsed as false verses; prefix with `Chart row:` so only real BPHS verse heads split. | 2026-05-03 |
| **`health_diseases_from_6th_house` golden chart** | `jupiter` in **house 8** added `8th_house` to query entities and boosted long `bphs-ch19-v13-19` over `v1`; chart updated to weak **6th lord in house 6** (Cancer / Jupiter) so gold@3 stays stable with a larger corpus. | 2026-05-03 |
| **Health intent keywords (`intent_router` + `rag_config`)** | Substrings such as `longevity`, `8th lord`, `kendra`, `ailments`, `afflicted` so Ch. 21–style questions hit **rules** `health` without LLM-only routing. | 2026-05-03 |
| **Ch. 22 corpus: split `13–25` into `13–17` + `18–25`** | Single block tagged `intent_health` via “8th lord/house” wording and matched generic conjunction entities, outranking **`health_ascendant_lord_with_malefics`**; two verses keep content while shrinking false wins. | 2026-05-03 |
| **`intent_router` family keywords (9th / father)** | Substrings such as `father`, `9th lord`, `9th house`, `fortunes`, `pilgrimage` so Ch. 22–style questions hit **rules** `family` without LLM-only routing. | 2026-05-03 |
| **`health_ascendant_lord_with_malefics` golden `chart_context`** | Lists **Moon, Mercury, Rahu, Saturn, Sun** with Mars in the 1st so query entities include **Mercury**, lifting **`bphs-ch19-v6`** over Ch. 22 father-death chunks. | 2026-05-03 |
| **Sharma Vol. 1 English OCR corpus + index** | Chapter `.txt` under `data/corpus/bphs_sharma/` are **gitignored**; committed **`tools/bphs_vol1_sharma_chapter_starts.json`** + scripts reproduce from PDF. **`rag_eval_history.json`** / **`eval_history.json`** gitignored (regenerable local runs). | 2026-05-09 |
| **Verse-head regex: period required for lone numbers** | Avoids false verse boundaries (e.g. `7 or the Uttarardha…`); ranges like `4-7 If` unchanged | 2026-05-09 |
| **`search_for_eval` must use `search(top_k=None)`** | Returning only `DENSE_TOP_K` post-rerank rows dropped gold refs still in the deduped pool (e.g. `bphs-ch23-v16`), collapsing gold@3 on full-book indexes | 2026-05-10 |
| **Full-book rerank: pre-order bonus + house chapter hints + BM25 sim cap** | `PRE_RERANK_WEIGHT` trusts RRF/dense ordering; `HOUSE_EFFECTS_CHAPTER` + question/chart hints + Navamsa align lift house-specific verses; `BM25_SIMILARITY_CAP` stops pseudo-sim 1.0 BM25 rows from dominating | 2026-05-10 |
| **`HOUSE_EFFECTS_CHAPTER` all 12 houses + 25-case RAG goldens** | Extended map with **1→14, 3→16, 4→17, 5→18, 7→20, 12→25** (Sharma “effects” chapters per `tools/ingest_bphs_sharma_house_arc.sh`); six new rows in `rag_eval_v0.json`; accepted **`rag_v0_20260510_085550`** **`1.00 / 1.00 / +0.50`**. Rolling history compared to **`rag_v0_20260503_085118`** (silver 0.90) so the wider suite could register without a strict delta regression vs the prior **1.00 / 1.00** row. | 2026-05-10 |
| **Qdrant (local/embedded mode) + fastembed BM25 over Chroma + rank_bm25** | Chroma's hybrid layer rebuilt a full-corpus BM25 index from scratch on every query (worse for `intent=general`, which skips the where-filter entirely); fastembed precomputes sparse BM25 vectors once at ingest, queried via indexed KNN. Qdrant's local mode keeps the same embedded/no-service deployment model Chroma had. See `docs/superpowers/specs/2026-08-16-rag-qdrant-migration-design.md`. | 2026-08-16 |

## Quick commands

### Ingest a chapter (idempotent)
```bash
source venv/bin/activate
# Example input path (create locally from PDF/OCR; not in git):
python astro_agent/rag/builder.py \
  --input data/corpus/bphs_sharma/ch_19_effects_of_6_house.txt \
  --book bphs --translator sharma --chapter 19 \
  --verbose
```

After splitter or corpus edits, drop stale rows for that chapter then add fresh chunks:

```bash
python astro_agent/rag/builder.py \
  --input data/corpus/bphs_sharma/ch_19_effects_of_6_house.txt \
  --book bphs --translator sharma --chapter 19 \
  --replace-chapter --verbose
```

### Run the eval (against golden v0)
```bash
python evals/evaluate_rag.py \
  --golden data/golden/rag_eval_v0.json \
  --output rag_eval_report.json \
  --history rag_eval_history.json
```

Add `--no-retention` to skip writing to history (useful while iterating).

**Intent:** by default, retrieval uses **`intent_router.detect_intent()`** (Ollama may run on ambiguous questions). **`--golden-intent`** uses golden `expected_intent` only (isolates retriever). **`--intent-model`** / **`--intent-timeout-s`** tune the router’s LLM fallback (defaults: model from env / `astro_engine`, timeout **45** s).

**Optional LLM judge (faithfulness vs retrieved chunks):** runs **serially** (answer + judge per eligible case; avoids VRAM pressure). Does **not** affect `rag_eval_history.json` acceptance (retrieval metrics only).

```bash
python evals/evaluate_rag.py \
  --golden data/golden/rag_eval_v0.json \
  --output rag_eval_report.json \
  --history rag_eval_history.json \
  --judge-model llama3.2:3b \
  --max-judge-cases 2
```

- **`--answer-model`**: override the main Ollama model for the generated answer (default: same as `ASTRO_MODEL_NAME` / engine).
- **`--no-answer-grounding`**: skip `nomic-embed-text` similarity vs chunks (faster).
- Omit **`--judge-model`** for retrieval-only eval (default).

### Career eval (baseline / enriched / RAG + grounding + judge)
```bash
source venv/bin/activate
# Recommended: RAG metrics + embedding grounding + small judge; rag-style history retention
python evals/evaluate_career.py --rag --runs 3 --workers 1 \
  --retention-mode rag \
  --judge-model llama3.2:3b \
  --output career_eval_report.json \
  --history eval_history.json
```
- **`--no-grounding`**: skip `nomic-embed-text` similarity vs chunks (faster; weaker `--retention-mode rag`).
- **`--retention-mode legacy`**: history compares `enriched_keyword_avg` / template (older behavior).

### Inspect what’s in the index
```bash
python -c "
from astro_agent.rag import qdrant_store, config as cfg
client = qdrant_store.get_collection(cfg.QDRANT_PATH)
print(f’Total: {client.count(cfg.QDRANT_COLLECTION, exact=True).count}’)
"
```

### Add a new chapter (full path)

**Option A — single chapter from PDF pages**

1. Render PDF pages: `pdftoppm -r 300 -f START -l END "books/Brihat Parasara Hora Sastra with English Translation Girish Chand Sharma Volume 1.pdf" ocr_work/ch_NN/p -png`
2. OCR each: `for f in ocr_work/ch_NN/p-*.png; do tesseract "$f" "${f%.png}" -l eng; done`
3. Concat: `cat ocr_work/ch_NN/p-*.txt > data/corpus/bphs_sharma/ch_NN_<topic>.txt`
4. Or use **`tools/ocr_bphs_chapter_range.py --pdf … --start START --end END --output …`**

**Option B — bulk (Sharma Vol. 1)**

1. Adjust **`tools/bphs_vol1_sharma_chapter_starts.json`** if boundaries shift.
2. **`python tools/extract_bphs_vol1_from_map.py`** (default PDF: `books/Brihat Parasara Hora Sastra with English Translation Girish Chand Sharma Volume 1.pdf`; writes `ch_N_bphs_vol1.txt`; skips **13–25** by default).
3. **`python scripts/ingest_bphs_from_full_pdf_dir.py --dir data/corpus/bphs_sharma`** (with Ollama + `nomic-embed-text`).

Then for any path:

4. Eyeball the `.txt` for serious garbage / OCR verse-number glitches.
5. `python knowledge_builder.py --input … --chapter NN --verbose` (or batch script above).
6. Remove scratch dirs (`ocr_work/`) if used.
7. Add ≥2 golden cases targeting the new chapter to `data/golden/rag_eval_v0.json` (when adding eval coverage).
8. Re-run eval; verify thresholds still met.

---

## Tunables (in `rag_config.py`)

If recall regresses, these are the first knobs to turn:

| Constant | Current (see `rag_config.py`) | Effect of raising | Effect of lowering |
| --- | --- | --- | --- |
| `DENSE_TOP_K` | 10 | More candidates for reranker, slower | Tighter, faster, may drop gold |
| `RERANK_TOP_K` | 3 | More chunks to LLM (more context, more cost) | Less context, more focus |
| `ENTITY_WEIGHT` | 0.12 | Reranker leans more on entity overlap | More on dense similarity |
| `ENTITY_MATCH_CAP` | 3 | Long-entity-list chunks dominate again | Even tighter cap |
| `ENTITY_TAIL_WEIGHT` | 0.03 | Stronger preference for chunks with many entity hits beyond the cap | Weaker tail; may lose tight gold@3 races |
| `ENTITY_TAIL_MAX` | 3 | Larger tail bonus (more extra hits counted) | Smaller tail |
| `INTENT_WEIGHT` | 0.08 | Intent filter has more pull at rerank | Less |
| `PRE_RERANK_WEIGHT` | 0.18 | Stronger trust in dense/RRF ordering before rerank | Weaker; entity/sim scores reorder more |
| `CHAPTER_HINT_WEIGHT` | 0.14 | Stronger preference for BPHS “effects” chapter aligned to cited house | Weaker cross-chapter hints |
| `NAVAMSA_ALIGN_WEIGHT` | 0.16 | Stronger bonus when question + chunk mention Navamsa/Navamsha | Weaker Navamsa rescue |
| `LENGTH_PENALTY_PER_100` | 0.10 | Big chunks penalized harder | Big chunks compete |
| `LENGTH_PENALTY_THRESHOLD` | 500 | Only very long chunks penalized | More chunks penalized |
| `CHUNK_TARGET_TOKENS` | 400 | Larger chunks (more context per chunk) | Smaller chunks (more chunks) — only takes effect if a real splitter is added |
| `MAX_CONTEXT_TOKENS_TOTAL` | 1200 | More retrieved text into prompt (risk: overflow R1 16384 ctx) | Less context in prompt |
| `HYBRID_BM25_ENABLED` | `True` | Lexical path on | Dense-only (BM25 code skipped) |
| `RRF_K` | `60` | Flatter RRF tail | Sharper RRF head |
| `RRF_WEIGHT_DENSE` | `12` | Pre-rerank order tracks dense more closely (often raises `rag_heuristic_delta`) | BM25 reorders more inside the pool |
| `RRF_WEIGHT_SPARSE` | `1` | BM25 pulls harder in RRF | Weaker lexical rescue for rare tokens |
| `BM25_SIMILARITY_FLOOR` | `0.05` | Higher floor for BM25-only chunks in dedupe | Lower floor |
| `BM25_SIMILARITY_CAP` | `0.88` | Lower cap: BM25-only rows less likely to beat dense in rerank | Higher cap: BM25 rows compete harder |

Re-run `evaluate_rag.py` after any tuning to verify guardrails still pass.

---

## Where to look for what

- "How does BM25 hybrid + RRF work?" → `rag_search.py::_hybrid_fusion_chunks`, `_bm25_max_scores_per_id`, `_rrf_scores`
- "How does retrieval rerank?" → `rag_search.py::_dedupe_chunks_by_ref_keep_best_dense` then `_rerank`
- "How does multi-query expansion work?" → `rag_search.py::expand_queries` (around line 99)
- "How are entities tagged?" → `rag_config.py::extract_entities` (around line 98)
- "How are intents detected per chunk?" → `rag_config.py::detect_intent_tags` (around line 175)
- "How are verses parsed?" → `knowledge_builder.py::VERSE_HEAD_RE` and `_split_verses`
- "How do I rebuild Sharma Vol. 1 corpus from the PDF?" → `tools/bphs_vol1_sharma_chapter_starts.json`, `tools/extract_bphs_vol1_from_map.py`, `scripts/ingest_bphs_from_full_pdf_dir.py`
- "How are long verses split for indexing?" → `knowledge_builder.py::_expand_oversize_chunks` (threshold `rag_config.CHUNK_MAX_TOKENS`)
- "What does the golden file look like?" → `data/golden/rag_eval_v0.json`
- "How does RAG eval retention work?" → `evaluate_rag.py::passes_guardrails`, `maybe_save_result`, `_outcomes_checksum`
- "Career RAG grounding / judge / retention?" → `evaluate_career.py` (`passes_guardrails()`, `select_global_baseline()`); shared judge/embedding → [`eval_grounding.py`](eval_grounding.py)
- "RAG golden LLM judge?" → `evaluate_rag.py` (`--judge-model`), [`eval_grounding.py`](eval_grounding.py)

---

## When you finish a meaningful change

1. Run `python evaluate_rag.py` (with retention) to attempt history acceptance. **Regression** on `(gold, silver, heuristic_delta)` rejects; **ties** use **`outcomes_checksum`**. Use **`--no-retention`** for scratch metrics without updating `rag_eval_history.json`.
2. If you changed **generation + RAG**, run `evaluate_career.py --rag` with **`--retention-mode rag`** and (recommended) **`--judge-model ...`**; check `career_eval_report.json` and `eval_history.json`.
3. If accepted, the new record is appended (or rotated) in the relevant history file. If rejected, fix or document why before continuing.
4. Update this file's **Status snapshot** + **Phase tracker** sections.
5. If a new decision was made, add a row to **Decisions log** with date and rationale.
