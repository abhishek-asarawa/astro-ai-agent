# RAG vector store migration: Chroma → Qdrant (local mode) design

Date: 2026-08-16  
Status: approved for planning

## Problem

The RAG retrieval pipeline (`astro_agent/rag/`) currently runs on ChromaDB
(embedded, local SQLite) with a hand-rolled BM25 hybrid layer: on every
`search()` call, `_hybrid_fusion_chunks` pulls the entire filtered corpus
slice out of Chroma, tokenizes it, and builds a fresh `rank_bm25.BM25Okapi`
index from scratch, then scores it against every expanded query variant
(`expand_queries` typically produces 2-5 variants per question). Nothing is
cached; it is rebuilt every request. For `intent="general"` queries,
`_intent_filter` returns no `where` filter at all, so this BM25 rebuild runs
over the *entire* corpus, not a subset.

At the current scale (~1.4k chunks, 1 book) this costs tens of milliseconds.
The user plans to ingest ~4 more astrology books (roughly 7-10k chunks
total). The BM25 rebuild cost scales with corpus size and is pure-Python,
CPU-bound, and uncached, on a machine already shared with Ollama and an LLM
process. This is the specific problem being fixed — not raw storage/query
capacity, which Chroma already handles comfortably at this scale.

## Goals

- Eliminate the per-query full-corpus BM25 rebuild by precomputing sparse
  (BM25) vectors once at ingest time and querying them via an indexed
  lookup instead.
- Preserve the embedded, no-background-service deployment model (no Docker
  daemon to start/stop, no persistent RAM baseline when the app isn't
  running) — this ruled out Weaviate (Docker-only, no embedded mode,
  docs recommend 8GB+ host RAM for local dev) during the spike that
  preceded this spec.
- Preserve retrieval quality: the migrated pipeline must meet or beat the
  currently accepted golden-eval numbers (`rag_recall_at_3_gold=1.00`,
  `rag_recall_at_5_silver=1.00`, `rag_heuristic_delta=+0.50`) via the
  existing `evals/evaluate_rag.py` harness before it becomes the default.
- Fix the `entities` metadata workaround (pipe-delimited string, because
  Chroma's `where` doesn't support list-contains) now that the same files
  are being rewritten anyway.
- Keep the migration a single clean cutover — no long-lived pluggable
  multi-backend abstraction.

## Non-goals

- Changing the RRF fusion algorithm's dense/sparse weighting behavior.
  Qdrant's native `FusionQuery(RRF)` doesn't support the weighting the
  current tuning relies on (`RRF_WEIGHT_DENSE=12` vs `RRF_WEIGHT_SPARSE=1`,
  chosen to keep pre-rerank order dense-shaped — see `RAG_PLAN.md`
  decisions log, 2026-05-03). Reusing the existing weighted-RRF math in
  Python, fed by two targeted Qdrant queries, keeps this a one-variable
  change (storage/indexing backend) instead of two (backend + fusion
  algorithm) — see Retrieval strategy below.
- Removing the manual dignity-alias hacks (`_DIGNITY_ENTITY_ALIASES`,
  `_bm25_expanded_queries`'s `"debilitation"`/`"navamamsha"` string
  appends). These exist because the current naive `_tokenize_bm25` regex
  tokenizer has no stemming. `fastembed`'s `Qdrant/bm25` model stems by
  default, which may make these partially redundant — that is a follow-up
  cleanup to consider only after this migration is validated, not part of
  it.
- Ingesting the remaining 4 books. That happens after this migration is
  validated and cut over, directly into Qdrant, per the decision to avoid
  tuning the reranker twice against two different backends.
- Cross-encoder reranking, query rewriting (HyDE-lite), or any other
  retrieval-quality feature not already shipped.
- Multi-user/concurrent query load. This is a single-user local app; the
  service-vs-embedded tradeoff was evaluated on that basis.

## Architecture

`astro_agent/rag/builder.py` (ingest) and `astro_agent/rag/search.py`
(retrieval) are rewritten against `qdrant-client` in local/embedded mode
(`QdrantClient(path="qdrant_db/")`) instead of `chromadb.PersistentClient`.
Local mode runs in-process with no separate server, and is documented as
suitable up to ~20,000 points per collection — comfortably above the ~7-10k
chunks expected across 5 books.

Every other consumer of the RAG pipeline — `astro_agent/rag/inject.py`,
`astro_agent/service/consultation.py`, `astro_agent/agent/loop.py`,
`astro_agent/agent/tools/__init__.py` — only calls the public
`rag_search.search()` / `search_for_eval()` functions and consumes
`RetrievedChunk` objects. Neither the function signatures nor the
`RetrievedChunk` shape change, so none of these files need to change.
`evals/evaluate_rag.py` and `evals/evaluate_career.py` likewise need no
changes — they exercise the same public API and will simply be running
against the new backend.

## Data model

- Collection: `vedic_corpus` (same name), one Qdrant point per chunk with
  two named vectors:
  - `dense`: 768-dim, cosine — unchanged, still `nomic-embed-text` via
    Ollama (`embed_text` / `embed_query` logic is untouched).
  - `bm25`: sparse vector via `fastembed`'s `Qdrant/bm25` model
    (`Modifier.IDF`), computed once per chunk at ingest time.
- Payload replaces Chroma's metadata dict:
  - `entities` becomes a native list field (was `|planet|house|...|`
    pipe-delimited string). `_parse_entities_field`'s split-on-`|` logic
    is removed; reranker entity-overlap code reads the list directly.
  - `book`, `translator`, `chapter`, `verse_start`, `verse_end`,
    `chunk_level`, `token_count`, `ref_id`, and the `intent_<name>`
    booleans carry over unchanged — Qdrant payloads support the same
    scalar/boolean types Chroma's metadata did.
- **Point ID scheme change.** Chroma accepts arbitrary string IDs, so
  `sha256(chunk_text)` was used directly, giving free idempotency on
  re-ingest. Qdrant point IDs must be an unsigned 64-bit int or a UUID
  string — a raw sha256 hex string is not a valid ID. Fix: derive a
  deterministic UUID via `uuid.uuid5(NAMESPACE_OID, sha256_hex)`. The same
  input text always produces the same UUID, so idempotency and
  `--replace-chapter` behavior are preserved unchanged; the sha256 hex
  itself is kept as a payload field (`content_hash`) for any future
  lookup/debug needs.

## Retrieval strategy

Per the Non-goals section, this intentionally does **not** adopt Qdrant's
native `FusionQuery(RRF)`. Instead, for each expanded query variant:

1. Run a dense-only `query_points` call against the `dense` vector
   (replaces `_dense_retrieve`).
2. Run a sparse-only `query_points` call against the `bm25` vector, using
   the query text encoded through the same `Qdrant/bm25` `fastembed` model
   used at ingest (replaces `_bm25_max_scores_per_id`'s from-scratch
   `BM25Okapi` build — this is the actual fix for the problem in scope).
3. Feed both ranked ID lists into the existing `_rrf_scores` /
   `_bm25_expanded_queries` weighting logic, unchanged
   (`RRF_K`, `RRF_WEIGHT_DENSE`, `RRF_WEIGHT_SPARSE` all carry over as-is).
4. Dedupe by `ref_id` (`_dedupe_chunks_by_ref_keep_best_dense`) and run the
   existing heuristic reranker (`_rerank_heuristic` /
   `_heuristic_scores_for_chunks`), unchanged — same entity/intent/
   chapter-hint/navamsa bonuses, same `PRE_RERANK_WEIGHT` decay term.

**Expected retuning, not a regression.** The current naive `_tokenize_bm25`
(plain `[A-Za-z0-9]+` regex, no stemming) is why manual hacks like
appending `"debilitation"` when the question contains `"debilitat"` exist.
`fastembed`'s `Qdrant/bm25` model stems by default, which changes what
matches and therefore the raw scores feeding `pre_rerank_rank`. Constants
in the "Tunables" table of `RAG_PLAN.md` — particularly
`BM25_SIMILARITY_FLOOR`/`BM25_SIMILARITY_CAP`, and possibly
`RRF_WEIGHT_DENSE`/`RRF_WEIGHT_SPARSE` — should be expected to need
re-tuning to hit the golden-eval bar again. This is normal, budgeted work,
not a sign the migration went wrong.

**Golden eval calibration rule (learned 2026-08 migration).** During the
Qdrant migration, four eval cases failed because their silver citations were
originally annotated against Chroma HNSW approximate-search outputs rather
than against actual chunk content. Chroma's approximate nearest-neighbor
produced false-positive high-similarity scores for topically irrelevant
chunks (e.g. a "Danda Yoga" verse ranking first for an argala query); the
eval annotators used those outputs as silver refs. Qdrant's exact cosine
search correctly does not reproduce those artifacts.

The rule to prevent this repeating: **every gold and silver citation must be
validated against the chunk's own text before being committed to the golden
dataset.** Specifically:

1. Read the candidate chunk's text and confirm it discusses the question's
   actual topic (not just a shared keyword or accidental high similarity).
2. Do not use "ranked near the top in the current eval run" as the sole
   selection criterion — retrieval backend changes will make such citations
   non-reproducible.
3. After verifying content relevance, confirm the ref_id exists in the
   current corpus via a Qdrant scroll query.

When a content-justified silver is not retrieved by the current system
(silver@5 miss), that is a retrieval gap to investigate — the correct
response is either (a) fix the retrieval or (b) document the gap and use the
best available content-justified alternative that the system does retrieve.
Do not move the goalposts by switching to whatever the system happens to
surface if that content is not topically relevant.

## Migration & validation plan

1. Add `qdrant-client` and `fastembed` to `requirements.txt`/`pyproject.toml`.
   Leave `chromadb` and the existing Chroma code paths untouched for now.
2. Write the new `builder.py` (ingest) and `search.py` (retrieval) against
   Qdrant, per the Data model and Retrieval strategy sections above.
3. Re-ingest the current BPHS corpus into `qdrant_db/` from the existing
   `.txt` sources under `data/corpus/bphs_sharma/` (already reproducible
   per the documented OCR pipeline — no data is lost by rebuilding from
   scratch).
4. Run `evals/evaluate_rag.py` unchanged. Gate: must meet or beat the
   currently accepted `(gold@3, silver@5, heuristic_delta) = (1.00, 1.00,
   +0.50)`. Re-tune the constants called out above if needed to clear the
   gate (see previous section).
5. Run `evals/evaluate_career.py --rag --retention-mode rag` as the
   secondary generation-quality check, per the existing "when you finish a
   meaningful change" checklist in `RAG_PLAN.md`.
6. On pass: delete `chroma_db/` and the `.gitignore` entry for it, remove
   `chromadb` from dependencies, delete any now-dead Chroma-specific code,
   and add a new entry to `RAG_PLAN.md`'s decisions log documenting the
   switch and why (mirroring the existing 2026-04-26 Chroma-over-Pinecone
   entry it supersedes).
7. Only after cutover: ingest the remaining ~4 books directly into Qdrant.

## Testing

- `evals/evaluate_rag.py` and `evals/evaluate_career.py` are the primary
  quality gate (Step 4-5 above) — no new eval infrastructure needed.
- New unit coverage for the two pieces that don't exist today:
  - UUID5 idempotency: same chunk text ingested twice produces the same
    point ID, no duplicate row, `--replace-chapter` still clears prior
    rows for a chapter correctly.
  - Dense+sparse two-query retrieval merge: given fixed fake dense/sparse
    query results, the merge produces `RetrievedChunk` objects with the
    same shape and `pre_rerank_rank` ordering semantics as the current
    Chroma-backed implementation, so `_rerank_heuristic` receives
    equivalent input.
- Existing tests referencing the RAG pipeline
  (`tests/test_rag_antardasha_entity.py`,
  `tests/test_intent_registry_and_config.py`,
  `tests/test_import_shim.py`) should continue to pass without
  modification, since `RetrievedChunk` and the public `search()` contract
  are unchanged; any failure there indicates an accidental interface
  change and should be treated as a bug, not updated to match.

## Rollback

Because this is a clean cutover done in a feature branch (not a dual-backend
flag), rollback is `git revert`/discard the branch — `chroma_db/` and the
Chroma code path are left untouched until Step 6, so nothing is destructive
until the golden-eval gate has already passed.
