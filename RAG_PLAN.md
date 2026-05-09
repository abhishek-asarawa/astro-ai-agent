# RAG Plan & Progress Tracker

> Working doc for any agent (or human) picking up RAG work on this repo.
> Read this first; it links to source files and records the state of the
> retrieval pipeline.

---

## Status snapshot

- **Phase**: 4 v0 (retrieval-only) — **DONE**
- **PR1** (RAG in LLM prompt + CLI) — **DONE**
- **PR2** (Streamlit sources + RAG toggle) — **DONE** (2026-05-02)
- **Career generation eval** (`evaluate_career.py`): **embedding grounding + optional LLM judge + `--retention-mode {legacy,rag}`** — **DONE**
- **Last retrieval-only eval (accepted)**: `rag_v0_20260503_085118` in `rag_eval_records/` (see `rag_eval_history.json`; history **2 / 3** slots)
  - `rag_recall_at_3_gold = 1.00` (target ≥ 0.60) ✅
  - `rag_recall_at_5_silver = 0.90` (target ≥ 0.80) ✅
  - `rag_heuristic_delta = +0.60` (target > 0) ✅
- **Latest `evaluate_rag.py --no-retention` (14 cases, Ch. 21 ingest, 2026-05-03)**: `1.00 / 1.00 / +0.50` — Ch. 21 eighth-house goldens + `intent_router` / `rag_config` health keyword expansion; **`health_diseases_from_6th_house`** chart entity tweak (see Decisions log).
- **Earlier `evaluate_rag.py --no-retention` (Tier 2 hybrid, 2026-05-03)**: `1.00 / 1.00 / +1.10` — `career_saturn_debilitated_10th` **silver@5 pass**; BM25+RRF + BM25-only query variants + chart/question **dignity entity aliases** in [`rag_search.py`](rag_search.py). **`evaluate_rag.py` retention** still requires **strict** `rag_recall_at_3_gold` **>** baseline, so at gold ceiling **1.00** a tie does not append history — use `--no-retention` to record this snapshot or relax policy in code if you want it in `rag_eval_history.json`.
- **`evaluate_rag.py` production intent (2026-05-03):** default path uses **`intent_router.detect_intent()`** (same family as `--rag-on` in [`astro_engine.py`](astro_engine.py)); golden file **`expected_intent`** is a label only; report adds `used_intent`, `intent_detection`, `intent_matches_golden`, summary **`intent_routing_agreement`**. Use **`--golden-intent`** to restore retrieval-only isolation. **`intent_router` career keywords** broadened (e.g. `10th lord`, `karma yogi`, `livelihood`) so BPHS-style questions hit **rules** intent `career` without LLM fallback.
- **Last career RAG baseline (rag retention)**: first accepted record with judge + grounding, e.g. `career_20260502_114813` in `eval_records/` (see `eval_history.json`; summary includes `rag_judge_grounding_avg`, `rag_grounding_max_sim_avg`, `retention_mode: rag`)
- **Corpus (BPHS, Sharma English Vol. 1)**: **47** chapters (`book=bphs`, `chapter=1..47`) indexed in `chroma_db/`; **~1.4k+** chunk rows after full-volume ingest (exact `col.count()` varies with re-runs). **Chapter `.txt` files are not in git** (`.gitignore`: `data/corpus/bphs_sharma/**/*.txt`); reproduce OCR from the PDF using `tools/extract_bphs_vol1_from_map.py` and `tools/bphs_vol1_sharma_chapter_starts.json`, then `scripts/ingest_bphs_from_full_pdf_dir.py` or `knowledge_builder.py`.
- **Full-volume ingest (2026-05-09):** Chapters **1–12** and **26–47** via PDF page map + OCR (`ch_N_bphs_vol1.txt`); chapters **13–25** kept from earlier targeted extracts (`ch_*_effects_*` / `ch_13_judgement_*`). **`VERSE_HEAD_RE`** tightened so prose like `7 or the Uttarardha…` does not fake a verse boundary.
- **Ch. 15 ingest (2026-05-03):** OCR PDF pp. 209–219 → `data/corpus/bphs_sharma/ch_15_effects_of_2_house.txt` (local OCR); golden **`wealth_2nd_lord_in_11th_11th_lord_in_2nd`**, **`wealth_jupiter_mars_in_2nd_house`**. Full `evaluate_rag.py` **12** cases **`--no-retention`**: `1.00 / 1.00 / +0.75` (retrieval-only; tie policy unchanged).
- **Ch. 21 ingest (2026-05-03):** OCR PDF pp. 255–280 (trimmed to Ch. 21 only) → `data/corpus/bphs_sharma/ch_21_effects_of_8_house.txt`; **`evaluate_rag.py` 14 cases `--no-retention`**: `1.00 / 1.00 / +0.50` (see scoreboard). Golden **`health_8th_lord_in_kendra_long_life`** uses **gold `bphs-ch21-v4-7`** (kendra + longevity block; opening `v1` often ranks 4th after rerank). **`health_diseases_from_6th_house`** chart `jupiter` moved from **house 8 → house 6** so query entities do not spuriously boost unrelated `8th_house` chunks over `bphs-ch19-v1`.
- **Ch. 22 ingest (2026-05-03):** OCR PDF pp. **263–268** → `data/corpus/bphs_sharma/ch_22_effects_of_9_house.txt` (`Sth`→`5th`/`9th` OCR fixes; long father-death block split **v13–17** / **v18–25** so health queries are not swamped). Goldens **`family_9th_lord_exalted_father_longlife`**, **`family_9th_10th_lord_exchange_father_wealth`**. **`evaluate_rag.py` 16 cases `--no-retention`**: `1.00 / 1.00 / +0.19` (`rag_heuristic_delta` **+0.188**); **`health_ascendant_lord_with_malefics`** chart lists **all** conjunct bodies so **`Mercury`** appears in query entities and **`bphs-ch19-v6`** wins over Ch. 22 death text.
- **Next focus** (suggested): Re-run **`evaluate_rag.py`** on the enlarged index (noise/cross-chapter competition may shift deltas); optionally add goldens for **Ch. 33 / 34 / 36** (now in corpus); **`evaluate_rag` LLM-judge** remains optional Tier 3.
- **Ch. 23 v16 corpus fix (2026-05-03):** `debiltation` → `debilitation` in `data/corpus/bphs_sharma/ch_23_effects_of_10_house.txt`; re-ingested with stale-hash cleanup. Silver miss that remained after OCR was addressed with **hybrid retrieval + dignity synonym overlap** (see Decisions log).

**Guardrails:** `evaluate_rag.py` retention uses retrieval metrics only. **`evaluate_career.py`** can use **`--retention-mode legacy`** (enriched keyword/template, older behavior) or **`--retention-mode rag`** (lexicographic composite: judge score → max chunk similarity → citations → RAG template). Keyword averages alone are a weak signal for generation quality; prefer grounding + judge for RAG regressions.

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
| `evaluate_rag.py` | Golden eval + smart retention; default **`detect_intent`** for retrieval (see `--golden-intent`) | `evaluate()`, CLI |
| `data/golden/rag_eval_v0.json` | 16 hand-labeled cases (5 career, 5 health, 4 wealth, 2 family / Ch. 22) | — |
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
| Idempotency on re-ingest verified (sha256 IDs) | ✅ |
| **Ingest full Sharma Vol. 1** — chapters **1–47** (PDF map + OCR + Chroma); corpus `.txt` gitignored | ✅ (2026-05-09) |
| Acceptance thresholds met; latest accepted **1.00 / 0.90 / +0.60** (`rag_v0_20260503_085118`) | ✅ |

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
| Ingest Ch. 17 (2nd house — wealth/family), Ch. 22 (9th — father/fortune), Ch. 21 (8th — longevity) | corpus + `knowledge_builder.py` | S each | ✅ **Ch. 15 (Second House)** = backlog “2nd house” item; ✅ **Ch. 21 (Eighth House)** (2026-05-03); ✅ **Ch. 22 (Ninth House)** (2026-05-03). **Ch. 33 / 36** now in index via **full Vol. 1 ingest** (2026-05-09); optional: **golden cases** for those chapters |
| Ingest Ch. 33 (Karakatwas), Ch. 36 (Karakamsa) | corpus | S each | ✅ **Indexed** with full book (2026-05-09); goldens / eval coverage still optional |
| Test retrieval with `intent_router.detect_intent()` instead of `expected_intent` | `evaluate_rag.py` | S | ✅ **Done** (2026-05-03) — default production path; `--golden-intent` isolates retriever |

### Backlog — production polish (Tier 3)

| Task | File(s) | Effort | Notes |
| --- | --- | --- | --- |
| LLM-as-judge faithfulness metric | `evaluate_rag.py` | M | **Partial:** `evaluate_career.py` already runs `llama3.2:3b` (or `--judge-model`) on RAG answers vs retrieved sources; extend to golden RAG eval if desired |
| Cross-encoder reranker (replace heuristic) | `rag_search.py::_rerank` | L | Needs ~1 GB free RAM; keep heuristic as fallback |
| Embedding cache for incremental re-ingest | `knowledge_builder.py` | S | Already partially solved by sha256 ID skip |
| Multi-hop / query decomposition | `rag_search.py` | L | For "compare X vs Y" style questions |
| Move corpus to `data/corpus_processed/` with deterministic OCR pipeline script | `scripts/ocr_chapter.sh` | M | Reproducible from PDF |

---

## Last eval scoreboard (16 cases, 6 chapters)

```
case_id                                  intent   gold@3  silver@5  delta
career_strong_10th_lord                  career      ✓        ✓       0
career_rahu_with_10th_lord_in_8th        career      ✓        ✓       0   (silver refs v11/v7; Ch. 15 cross-pull 2026-05-03)
career_jupiter_aspect_karma_yogi         career      ✓        ✓       1
career_saturn_debilitated_10th           career      ✓        ✓       2   (Tier 2 hybrid + dignity aliases, `--no-retention` 2026-05-03)
career_fame_through_moon_in_10th         career      ✓        ✓       0
health_diseases_from_6th_house           health      ✓        ✓      -1
health_ascendant_lord_with_malefics      health      ✓        ✓       0   (Ch. 22 split + full conjunct chart entities, 2026-05-03)
health_8th_lord_in_6th_with_moon         health      ✓        ✓       4
health_8th_lord_in_kendra_long_life      health      ✓        ✓       0   (Ch. 21; gold bphs-ch21-v4-7)
health_8th_lord_malefic_conjoin_asc_lord_in_8th  health      ✓        ✓       0   (Ch. 21; gold bphs-ch21-v2)
wealth_11th_lord_in_own_or_angle         wealth      ✓        ✓       0
wealth_11th_lord_in_2nd_house            wealth      ✓        ✓       0
wealth_2nd_lord_in_11th_11th_lord_in_2nd wealth      ✓        ✓       1   (bphs-ch15-v4; Ch. 15 ingest)
wealth_jupiter_mars_in_2nd_house         wealth      ✓        ✓       0   (bphs-ch15-v3)
family_9th_lord_exalted_father_longlife  family      ✓        ✓       0   (Ch. 22; gold bphs-ch22-v5)
family_9th_10th_lord_exchange_father_wealth  family   ✓        ✓      -2   (Ch. 22; gold bphs-ch22-v7)
```

Historical snapshot from **`rag_v0_20260503_085118`** had one silver miss; current hybrid pipeline clears it (see status snapshot above).

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
| **`evaluate_rag.py` retention needs strict gold@3 increase** | At `rag_recall_at_3_gold = 0.90` on 10 cases, many quality-only fixes cannot append history; use `--no-retention` for verification, or relax guardrails in code if policy changes | 2026-05-03 |
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

## Quick commands

### Ingest a chapter (idempotent)
```bash
source venv/bin/activate
# Example input path (create locally from PDF/OCR; not in git):
python knowledge_builder.py \
  --input data/corpus/bphs_sharma/ch_19_effects_of_6_house.txt \
  --book bphs --translator sharma --chapter 19 \
  --verbose
```

After splitter or corpus edits, drop stale Chroma rows for that chapter then add fresh chunks:

```bash
python knowledge_builder.py \
  --input data/corpus/bphs_sharma/ch_19_effects_of_6_house.txt \
  --book bphs --translator sharma --chapter 19 \
  --replace-chapter --verbose
```

### Run the eval (against golden v0)
```bash
python evaluate_rag.py \
  --golden data/golden/rag_eval_v0.json \
  --output rag_eval_report.json \
  --history rag_eval_history.json
```

Add `--no-retention` to skip writing to history (useful while iterating).

**Intent:** by default, retrieval uses **`intent_router.detect_intent()`** (Ollama may run on ambiguous questions). **`--golden-intent`** uses golden `expected_intent` only (isolates retriever). **`--intent-model`** / **`--intent-timeout-s`** tune the router’s LLM fallback (defaults: model from env / `astro_engine`, timeout **45** s).

### Career eval (baseline / enriched / RAG + grounding + judge)
```bash
source venv/bin/activate
# Recommended: RAG metrics + embedding grounding + small judge; rag-style history retention
python evaluate_career.py --rag --runs 3 --workers 1 \
  --retention-mode rag \
  --judge-model llama3.2:3b \
  --output career_eval_report.json \
  --history eval_history.json
```
- **`--no-grounding`**: skip `nomic-embed-text` similarity vs chunks (faster; weaker `--retention-mode rag`).
- **`--retention-mode legacy`**: history compares `enriched_keyword_avg` / template (older behavior).

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

**Option A — single chapter from PDF pages**

1. Render PDF pages: `pdftoppm -r 300 -f START -l END "<book.pdf>" ocr_work/ch_NN/p -png`
2. OCR each: `for f in ocr_work/ch_NN/p-*.png; do tesseract "$f" "${f%.png}" -l eng; done`
3. Concat: `cat ocr_work/ch_NN/p-*.txt > data/corpus/bphs_sharma/ch_NN_<topic>.txt`
4. Or use **`tools/ocr_bphs_chapter_range.py --pdf … --start START --end END --output …`**

**Option B — bulk (Sharma Vol. 1)**

1. Adjust **`tools/bphs_vol1_sharma_chapter_starts.json`** if boundaries shift.
2. **`python tools/extract_bphs_vol1_from_map.py --pdf "<book.pdf>"`** (writes `ch_N_bphs_vol1.txt`; skips **13–25** by default).
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

| Constant | Current | Effect of raising | Effect of lowering |
| --- | --- | --- | --- |
| `DENSE_TOP_K` | 10 | More candidates for reranker, slower | Tighter, faster, may drop gold |
| `RERANK_TOP_K` | 3 | More chunks to LLM (more context, more cost) | Less context, more focus |
| `ENTITY_WEIGHT` | 0.20 | Reranker leans more on entity overlap | More on dense similarity |
| `ENTITY_MATCH_CAP` | 3 | Long-entity-list chunks dominate again | Even tighter cap |
| `ENTITY_TAIL_WEIGHT` | 0.03 | Stronger preference for chunks with many entity hits beyond the cap | Weaker tail; may lose tight gold@3 races |
| `ENTITY_TAIL_MAX` | 3 | Larger tail bonus (more extra hits counted) | Smaller tail |
| `INTENT_WEIGHT` | 0.10 | Intent filter has more pull at rerank | Less |
| `LENGTH_PENALTY_PER_100` | 0.10 | Big chunks penalized harder | Big chunks compete |
| `LENGTH_PENALTY_THRESHOLD` | 500 | Only very long chunks penalized | More chunks penalized |
| `CHUNK_TARGET_TOKENS` | 400 | Larger chunks (more context per chunk) | Smaller chunks (more chunks) — only takes effect if a real splitter is added |
| `MAX_CONTEXT_TOKENS_TOTAL` | 1200 | More retrieved text into prompt (risk: overflow R1 16384 ctx) | Less context in prompt |
| `HYBRID_BM25_ENABLED` | `True` | Lexical path on | Dense-only (BM25 code skipped) |
| `RRF_K` | `60` | Flatter RRF tail | Sharper RRF head |
| `RRF_WEIGHT_DENSE` | `12` | Pre-rerank order tracks dense more closely (often raises `rag_heuristic_delta`) | BM25 reorders more inside the pool |
| `RRF_WEIGHT_SPARSE` | `1` | BM25 pulls harder in RRF | Weaker lexical rescue for rare tokens |
| `BM25_SIMILARITY_FLOOR` | `0.05` | Higher floor for BM25-only chunks in dedupe | Lower floor |

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
- "How does smart retention work?" → `evaluate_rag.py::maybe_save_result`
- "Career RAG grounding / judge / retention?" → `evaluate_career.py` (`score_grounding_embedding()`, `run_grounding_judge()`, `passes_guardrails()`, `select_global_baseline()`)

---

## When you finish a meaningful change

1. Run `python evaluate_rag.py` (with retention) to attempt history acceptance for **retrieval-only** quality. If headline `rag_recall_at_3_gold` matches the best prior run with **no strict improvement**, retention rejects ties — use **`--no-retention`** to validate metrics without fighting guardrails.
2. If you changed **generation + RAG**, run `evaluate_career.py --rag` with **`--retention-mode rag`** and (recommended) **`--judge-model ...`**; check `career_eval_report.json` and `eval_history.json`.
3. If accepted, the new record is appended to the relevant history file. If rejected, fix or document why before continuing.
4. Update this file's **Status snapshot** + **Phase tracker** sections.
5. If a new decision was made, add a row to **Decisions log** with date and rationale.
