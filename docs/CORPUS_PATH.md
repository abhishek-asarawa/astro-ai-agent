# Multi-book RAG corpus path

> Product backlog lives in [FUTURE_IMPROVEMENTS.md](FUTURE_IMPROVEMENTS.md).
> Feature definitions live in [specs/](specs/). This note records the **engineering path** for multi-book retrieval before dosha/remedy features ship.

## Goal

Support citing more than BPHS Vol.1 (Phaladeepika, Lal Kitab, Muhurta, etc.) without breaking existing `[ref:bphs-…]` citations.

## Already in code

- `astro_agent.rag.config.BOOK_CITATION_PREFIX` — book id → citation prefix map
- `astro_agent.rag.config.DOSHA_REMEDY_ENTITY_TERMS` — dosha/remedy/matching vocabulary wired into `extract_entities()`
- Intent keywords centralized in `astro_agent.intents` (`RAG_INTENT_KEYWORDS` for ingest tagging)

## Remaining work (do before enabling dosha/remedy UX)

1. Per-corpus `manifest.json` under `data/corpus/<book>/` with chapter→house maps (replace BPHS-only `HOUSE_EFFECTS_CHAPTER` hardcoding over time).
2. Ingest CLI: accept `--book <id>` and write `book` metadata on every Chroma row.
3. `rag_search.search()`: optional `book` filter via Chroma `where`.
4. Citation allowlist: accept prefixes from `BOOK_CITATION_PREFIX`, not only `bphs-`.
5. Golden set: add Manglik / Sade Sati / remedy cases once corpora are ingested; gate on `evaluate_rag` / real-world evals.

## Acceptance (from FUTURE_IMPROVEMENTS)

- Phaladeepika + Lal Kitab ingested with ≥80% retrieval@3 on a dosha/remedy golden set
- Entity extractor recognizes dosha/remedy terms listed in FUTURE_IMPROVEMENTS §1.3
- Real-world v1 re-adds deferred dosha/remedy questions
