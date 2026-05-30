# Future Improvements

> Backlog of deferred work. New ideas should be appended here, not lost in chat.
> For in-flight production work see [AGENT_PROD_PLAN.md](AGENT_PROD_PLAN.md);
> for RAG pipeline state see [RAG_PLAN.md](RAG_PLAN.md).

---

## Why this doc exists

The Real-World Questions Benchmark (Phase 1) ships scoped to what BPHS Vol.1 can actually ground. Several real-world question categories, router enrichments, and architectural improvements were deliberately deferred to keep that PR focused. This file is where they live until prioritized.

---

## 1. RAG corpus expansion

**Problem**: Current corpus is BPHS Vol.1 only ([data/corpus/bphs_sharma/](data/corpus/bphs_sharma/)). Several India-trending question categories have **zero grounding** in BPHS and would cause silent hallucination if asked today.

### 1.1 Deferred question categories

These were dropped from the real-world benchmark because the model has no corpus to ground them in. Once corpus is expanded, re-introduce them as `data/golden/real_world_questions_v1.json`.

#### Dosha questions
- `"Am I manglik and will it affect my marriage?"`
- `"What are the remedies for Mangal Dosha?"`
- `"Am I going through Sade Sati right now?"`
- `"When will my Sade Sati end?"`
- `"Do I have Kaal Sarp Dosha in my chart?"`
- `"What remedies should I do for Pitru Dosha?"`
- `"Is Shani Dhaiya affecting me?"`

Source attribution for v1: astrosage.com, siyaswayamver.com, bookmypoojaonline.com, timesofindia.indiatimes.com/astrology, shloka.life.

#### Matching / compatibility questions
- `"What is our Guna Milan score and should we proceed with this match?"`
- `"How many gunas match in our kundali?"`
- `"Is our Nadi Dosha cancelled?"`
- `"What is our Ashtakoot compatibility?"`

#### Remedy questions
- `"Which gemstone should I wear to remove obstacles in marriage?"`
- `"What puja or mantra will help my career?"`
- `"Should I wear yellow sapphire?"`
- `"Which yantra is suitable for my chart?"`
- `"What charity should I do on Saturdays?"`

### 1.2 Candidate corpora to ingest

| Source text | Coverage gained | Notes |
|---|---|---|
| **Phaladeepika** (Mantreswara) | Predictive timing rules, Sade Sati, transit doctrine | Standard companion to BPHS in modern practice |
| **Lal Kitab** | Remedies (gemstone, puja, mantra), Manglik treatment | Mass-market remedy framework popular in North India |
| **Muhurta Chintamani** | Guna Milan, Ashtakoot matching, auspicious timing | Source-of-truth for kundali matching |
| **Saravali** (Kalyana Varma) | Yogas, additional predictive techniques | Complementary to BPHS |
| **Uttara Kalamrita** (Kalidasa) | Refined dasha results, prashna | Concise reference text |
| **Brihat Jataka** (Varahamihira) | Classical Sanskrit foundation | Adds doctrinal weight |
| **Ratnashastra** (texts on gemology) | Gemstone-planet correspondence | Required for remedy-grounded responses |

### 1.3 Pipeline changes required alongside corpus expansion

Just ingesting the PDFs is not enough. The following code paths must be updated:

1. **[rag_config.py](rag_config.py) `extract_entities()`** (lines 218-261) — hardcoded regex for Vedic terms (planets, signs, houses, dignities, aspects). Add regex patterns for:
   - `manglik`, `mangal dosha`, `kuja dosha`
   - `sade sati`, `shani dhaiya`, `shani sade sati`
   - `kaal sarp`, `kaal sarp yog`, `kaal sarp dosha`
   - `pitru dosha`, `pitra dosha`
   - `guna milan`, `ashtakoot`, `nadi dosha`, `bhakoot`
   - Gemstones: `yellow sapphire`, `pukhraj`, `ruby`, `manik`, `emerald`, `panna`, `red coral`, `moonga`, `pearl`, `moti`, `diamond`, `heera`, `rudraksha`
   - Remedy verbs: `puja`, `havan`, `yantra`, `mantra`, `chant`, `fasting`, `donation`, `charity`

2. **[rag_config.py](rag_config.py) `INTENT_KEYWORDS`** (lines 264-292) — same expansion so dosha/remedy chunks get tagged with the correct intent at ingest time. Without this, dosha chunks remain untaggable even after ingest.

3. **`HOUSE_EFFECTS_CHAPTER`** mapping (lines 67-80) — currently BPHS-Sharma-Vol1 specific. Each new corpus needs its own chapter→house mapping or a unified taxonomy. Consider moving to `data/corpus/<book>/manifest.json` per corpus.

4. **[knowledge_builder.py](knowledge_builder.py)** ingest CLI — verify the verse-boundary regex handles non-BPHS text structures (Lal Kitab uses farman-style numbered statements, Muhurta uses tables).

5. **Per-book metadata field** — add `book` filter to chroma queries so career questions can be answered from BPHS while remedy questions pull from Lal Kitab. Cross-book retrieval can dilute relevance.

6. **Citation format** — current `[ref:bphs-chXX-vYY]` format must extend to multi-book: `[ref:lalkitab-fYY]`, `[ref:phaladeepika-chXX]`, etc.

### 1.4 Acceptance criteria for "corpus expansion done"

- At least Phaladeepika + Lal Kitab ingested with ≥80% retrieval@3 on a Manglik / Sade Sati / gemstone golden set
- `rag_config.py extract_entities()` recognizes all dosha and remedy terms listed in §1.3.1
- `data/golden/real_world_questions_v1.json` re-adds the 9 deferred cases from §1.1
- `evaluate_real_world_questions.py` `intent_accuracy_per_tag` shows ≥85% on `dosha` and `remedy` tags

---

## 2. Intent system improvements

### 2.1 Single source of truth for intents (currently scattered in 6 files)

`SUPPORTED_INTENTS` is duplicated across:
- [intent_router.py](intent_router.py) line 6
- [rag_config.py](rag_config.py) line 62
- [rag_search.py](rag_search.py)
- [prompts/builder.py](prompts/builder.py) (intent_map)
- [eval_template_markers.py](eval_template_markers.py) (TEMPLATE_MARKERS)
- [evaluate_intent_routing.py](evaluate_intent_routing.py)

**Proposed**: a new `intents.py` module with a single `SUPPORTED_INTENTS` tuple plus a `validate_intent_registry()` function called at import time that asserts every intent has matching entries in `INTENT_KEYWORDS`, `intent_map`, and `TEMPLATE_MARKERS`. Prevents partial-rollout class of bugs.

### 2.2 Split `family` → `relationship` + `family` (gated)

Marriage/spouse questions are the #1 asked topic in every source but currently share the `family` bucket with parents/siblings/home questions. Astrologically these are 7th house vs 4th house — completely different signatures.

**Trigger condition**: if Phase 1 benchmark shows `intent_accuracy_per_tag` for `marriage` < 85% OR response quality clearly degraded on marriage cases vs home cases, execute the split.

**Scope when triggered**:
- New `relationship` builder in [prompts/builder.py](prompts/builder.py) using 7th/5th/2nd/8th houses
- Narrow `family` builder to 4th/3rd/5th/9th
- Relabel two existing cases: `route_family_1` in [evaluate_intent_routing.py](evaluate_intent_routing.py) and `family_chennai_1991` + `family_mumbai_1992` in [evaluate_career.py](evaluate_career.py)
- Bump golden file to v1

### 2.3 Add `education` intent (gated)

Currently education questions misroute to `career` or `general`. They are common in Indian astrology consultations (UPSC, IIT, NEET, admissions). Distinct factors: 4th house (basics), 5th house (intelligence), Mercury, Jupiter.

Same trigger gating as §2.2.

### 2.4 Considered but rejected as separate intents

- **`remedies`** — cross-cutting (a remedy is asked inside another domain context). Handle as a response section inside each domain prompt instead.
- **`dosha`** — Manglik is a relationship diagnostic, Sade Sati is general-life, Kaal Sarp is general, Pitru Dosha is family. Each maps to an existing intent; only vocabulary needs to grow.
- **`property`** — low volume, overlaps wealth's 2nd/4th house factors.

---

## 3. Scoring and evaluation improvements

### 3.1 Lemmatized / synonym-aware keyword scoring

Current `score_keyword_coverage` (originally in [evaluate_intent_routing.py](evaluate_intent_routing.py) lines 64-69 and [evaluate_career.py](evaluate_career.py) lines 124-129) does naive substring match. `"transit"` matches `"transits"` but not `"movement"`. Brittle and underestimates good responses.

**Proposed**: add a synonyms map per keyword, or integrate a lightweight lemmatizer (no new deps if we use stdlib `difflib.get_close_matches` with cutoff).

### 3.2 Real-user-question harvesting

[tracer.py](tracer.py) logs every user interaction to `interactions.jsonl` (line 109) when `ASTRO_TRACE_ENABLED=1`. Once a few hundred have accumulated, harvest distinct phrases to seed `real_world_questions_v1.json`. This grounds the benchmark in actual user language rather than astrologer-marketing SEO content.

Suggested helper: extend [scripts/interaction_summary.py](scripts/interaction_summary.py) with a `--export-golden-candidates` flag that emits a JSON skeleton with auto-detected expected_intent (rule-based) for human review.

### 3.3 CLI argparse deduplication

Every evaluator script has near-identical `parse_args()` blocks with `--model`, `--timeout`, `--workers`, `--num-ctx`, `--output`. Extract to `eval_cli.py` with a `build_evaluator_parser(description)` helper. Reduces drift when adding new flags.

### 3.4 Output report directory hygiene

Existing evaluators dump `*_eval_report.json` to repo root, polluting `ls`. Should move all under `eval_records/` (already exists for career runs). New `evaluate_real_world_questions.py` already does this in Phase 1; backfill the others.

### 3.5 Schema validation across all golden files

Phase 1 adds `data/golden/schema.py` with a `GoldenCase` dataclass and `from_dict()` validator for `real_world_questions_v0.json`. The existing [data/golden/rag_eval_v0.json](data/golden/rag_eval_v0.json) should be migrated to the same schema. Field gaps (it uses `gold_citations` and `silver_citations` not present in `GoldenCase`) suggest a `RagGoldenCase` subclass or shared base.

---

## 4. Architectural improvements

### 4.1 Multi-turn memory injection (carried over from AGENT_PROD_PLAN)

Chat history is collected in [app.py](app.py) `st.session_state.chat_history` but never injected into prompts. The `prior_context` parameter exists in every `build_*_prompt` function but app code does not populate it. Wire it up.

### 4.2 Per-book retrieval filtering

After §1 (multi-corpus), retrieval should accept a `book` filter so career questions don't pull Lal Kitab chunks and remedy questions don't pull BPHS jurisprudence chapters. ChromaDB already supports metadata `where` filters; just expose it in `rag_search.search()`.

### 4.3 Cross-encoder rerank by default

[rag_config.py](rag_config.py) line 110 has `CROSS_ENCODER_RERANK_ENABLED = False`. Evaluate whether enabling it improves multi-corpus retrieval after §1. The model is already CPU-friendly (~80MB ms-marco MiniLM).

### 4.4 Documentation consolidation

Three trackers exist: [README.md](README.md), [AGENT_PROD_PLAN.md](AGENT_PROD_PLAN.md), [RAG_PLAN.md](RAG_PLAN.md). Plus this file. Consider consolidating after Phase 2 of the benchmark into a `docs/` folder with `docs/EVALS.md`, `docs/RAG.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`.

---

## 5. Out-of-scope but tracked

- **Tamil / Telugu / Kannada astrology terminology** (Sevvai Dosham, etc.) for regional users
- **KP system (Krishnamurti Paddhati)** support — different sub-lord calculation methodology
- **Nadi astrology** support (Bhrigu Nadi, Agastya Nadi)
- **Western astrology** modules (psychological natal, synastry, composite) — different audience
- **Prashna Kundali** (horary) — answers without birth chart, different code path
- **Voice / audio input** in Streamlit UI for accessibility
- **Multi-language UI** (Hindi, Tamil, Telugu)
- **Subscription / paywall** patterns if this ever goes to production
- **Privacy / PII handling** review on `interactions.jsonl` before any cloud deployment

---

## How to use this doc

- New ideas: append to the relevant section above
- When picking up work: copy a section to a new plan, link back here, and mark this section "in flight"
- When work ships: remove the section from here, update [AGENT_PROD_PLAN.md](AGENT_PROD_PLAN.md) status
