# Astro AI Agent — Product Roadmap

> **For agents and contributors: read this first.** This is the backbone of the
> project. It says *where we are going* and *in what order*. Feature behavior
> lives in [docs/specs/](specs/README.md); coding rules live in
> [docs/standards/](standards/README.md); each step below gets its own spec and
> plan before code is written.
>
> - Baseline: `main` @ `a61e26d` (2026-10-20)
> - Current milestone: **M1 — MVP**
> - Tracking: GitHub Milestones `M1`–`M6`, one epic issue per milestone, one
>   sub-issue per step (see [§8](#8-github-mapping)).

---

## 1. Vision

An **agentic RAG chatbot for Hindu (Vedic / Jyotish) astrology** that helps a
person understand and navigate everyday problems — career, money, health,
relationships, family, timing of decisions — by reading their birth chart and
grounding every interpretation in the **classical texts** (Brihat Parashara
Hora Shastra, Brihat Jataka, Saravali, Phaladeepika, and the rest of the
canon).

It should feel like a complete chatbot product: streaming answers, saved
profiles and conversations, visible citations, chart visuals, daily guidance,
multiple languages — and eventually be safe to run publicly for real users.

**Delivery order (agreed):** MVP → Foundation & knowledge → Beautiful UI →
Every classical book → Hindi/Hinglish → Go public.

## 2. Product principles

These hold across every milestone. If a change conflicts with one, raise it
before building.

1. **Grounded, not invented.** Interpretations cite the classical texts. Claims
   about the user's chart must match the computed chart — the LLM never
   invents placements.
2. **Guidance, not fate.** Answer astrology questions fully (health, longevity,
   remedies included) while avoiding a narrow set of harmful moves — see the
   guidance policy (decision D11, step M1.3).
3. **Local-first, public-ready.** Everything runs on one machine today
   (Ollama, embedded Qdrant, SQLite). Every design keeps a clean seam so the
   same code can be hosted later (cloud LLM, Qdrant server, Postgres, auth).
4. **Deterministic astrology math.** Chart, dasha, transit, matching, and dosha
   calculations are plain tested code, validated against reference software —
   never delegated to the LLM.
5. **Evals are the quality gate.** No model, prompt, retrieval, or framework
   change merges if it regresses the golden evals. Every new capability ships
   with golden cases.
6. **Own the core, rent the plumbing.** Domain logic, retrieval, and model calls
   are our code; frameworks are used for plumbing only (see D4).
7. **Every book is traceable.** Each ingested book carries a manifest with its
   edition and licence status.

## 3. Where we are today (baseline 2026-10-20)

| Area | State |
|------|-------|
| Chart engine | Swiss Ephemeris; lagna, planets, lords, yogas, bhava chalit, Vimshottari maha + antar dasha, timing windows (`astro_agent/chart/`) |
| Intent routing | Hybrid rules + `llama3.2:3b` fallback; intents `career, health, wealth, family, general` (`astro_agent/intents.py`) |
| RAG | Qdrant embedded, dense (`nomic-embed-text`) + fastembed BM25 sparse, heuristic + optional cross-encoder rerank, citation validation; corpus = **BPHS Vol 1 only** (1,399 chunks) |
| Agent | Custom ReAct tool loop (`astro_agent/agent/loop.py`), tools: `build_chart`, `rag_search`, `get_dasha`, `get_timing_window`, `detect_intent`; linear fallback |
| LLM | Ollama local, `qwen2.5:7b-instruct` |
| UI | Streamlit chat (`app.py`) over `astro_agent.service.run_consultation` |
| Quality | Golden sets (`data/golden/`), RAG eval gold@3 = 1.00 / silver@5 = 1.00, career eval, intent eval, real-world eval; ruff + mypy + pytest CI; spec-driven commit gate |
| Live specs | `career-guidance`, `timing-windows` |
| Planned specs | `manglik-detection`, `sade-sati`, `guna-milan-matching`, `remedies` |
| Open issues | #2, #3, #4, #5 (grounding/citations/tests), #6 (stale doc paths) |

Historical context: [AGENT_PROD_PLAN.md](AGENT_PROD_PLAN.md) (phases 1–7,
complete), [RAG_PLAN.md](RAG_PLAN.md), [CORPUS_PATH.md](CORPUS_PATH.md).
Engineering backlog: [FUTURE_IMPROVEMENTS.md](FUTURE_IMPROVEMENTS.md) — items
promoted into this roadmap are referenced by step ID.

## 4. Decision log

Append-only. To change a decision, add a new entry that supersedes the old one
(and say so) rather than editing history.

| ID | Date | Decision | Rationale |
|----|------|----------|-----------|
| D1 | 2026-10-20 | **Local-first, designed to go public later.** Accounts, hosting, billing arrive in M6. | Build value cheaply now without painting into a corner. |
| D2 | 2026-10-20 | **Milestone ladder with exit gates.** Six milestones in fixed order; each closes only when its measurable gate is verified. | Unambiguous progress; little rework; matches eval-gated culture. Rejected: vertical slices per life theme (UI and ingest rebuilt per slice), platform-first (months with no answer-quality gains). |
| D3 | 2026-10-20 | **MVP includes the backend API** (FastAPI + streaming + agent-runner contract). | The UI milestone builds on a stable interface without rework. |
| D4 | 2026-10-20 | **Agent framework: custom loop through M1; LangGraph from M2.3.** LangGraph runs the agent graph (state, checkpointing, interrupts, streaming, subgraphs). Model calls, retrieval, and chart math stay our own code — no LangChain model wrappers, vector stores, retrievers, prompt templates, parsers, or loaders. Adopting any LangChain component later needs a short ADR. | LangGraph gives persistence, human-in-the-loop interrupts, and step streaming we'd otherwise hand-build. Our retrieval and Ollama call path are tuned and eval-calibrated; generic wrappers would regress them. Keeps lock-in to the graph wiring. Not in MVP so eval regressions stay attributable. Considered: PydanticAI (less mature persistence/interrupts), Claude Agent SDK (single-provider). |
| D5 | 2026-10-20 | **UI: Next.js + TypeScript + Tailwind + shadcn/ui.** Streamlit stays as an internal dev console. | Polished, mobile-ready, public-ready UI. Chainlit rejected as too limiting. |
| D6 | 2026-10-20 | **App data: SQLite via SQLAlchemy + Alembic now; Postgres in M6.** | Same repository layer both places. |
| D7 | 2026-10-20 | **Vector store: Qdrant embedded now; Qdrant server in M6.** Hybrid dense + BM25 sparse retained. | Same client code; migration done in PR #9. |
| D8 | 2026-10-20 | **Model providers behind one interface (M2.1):** Ollama default locally; Claude (cloud) available; production choice made from the eval matrix in M6. | Swap by config; compare quality vs cost with data. |
| D9 | 2026-10-20 | **English first; Hindi + Hinglish in M5.** Multilingual embedding model chosen in M2.5 so M5 is cheap. | Focus MVP on quality; avoid re-indexing later. |
| D10 | 2026-10-20 | **Book licensing: personal-use ingest allowed now; licence status recorded per book; public deployment gated (M6.1).** Licence values: `public-domain`, `licensed`, `owned-personal-use`, `unknown`. | Use the best translations now; make the go-public check mechanical. |
| D11 | 2026-10-20 | **Guidance policy: answer fully, avoid narrow harms, one hard crisis rule** (table in M1.3). Enforced by a *two-sided* eval: must-answer cases fail on refusal or empty hedging. | Health, longevity, and remedies are core user questions; blanket refusals would kill the product. |
| D12 | 2026-10-20 | **This file is the single roadmap.** Detail is rolling-wave: the current milestone has fine-grained todos; later milestones are refined at kickoff. | Avoid stale six-months-out detail and drift between docs. |

## 5. Milestone overview

| # | Milestone | Goal | Exit gate (summary) | Status |
|---|-----------|------|---------------------|--------|
| M1 | **MVP** | Trustworthy, complete core: grounding bugs fixed, guidance policy, Manglik / Sade Sati / Guna Milan / Remedies live, saved profiles, FastAPI backend | #2–#6 closed; 4 specs live; RAG gold@3 ≥ 1.00; dosha set retrieval@3 ≥ 0.8; must-not 100% / must-answer ≥ 95%; Streamlit only via API | **Active** |
| M2 | **Foundation & knowledge** | Provider abstraction, LangGraph, multi-book pipeline, knowledge base, complete chart engine, stronger agent, storage, observability | Provider swap passes evals; LangGraph parity; BPHS Vol 2 pilot ≥ 0.8; chart calcs match reference on ≥ 20 charts; 0 chart-fact contradictions | Not started |
| M3 | **Beautiful chat UI** | Next.js product UI with streaming chat, citations, chart visuals, profiles, history, daily guidance | All M1/M2 capabilities in UI; Playwright green; Lighthouse ≥ 90; first event ≤ 1 s; 5 scripted tasks unaided | Not started |
| M4 | **Classical library** | Ingest every pioneer book (Tier 1 + Tier 2) with per-book evals and cross-book reasoning | All Tier 1/2 ingested with manifests; each ≥ 0.8 retrieval@3; no regression; disagreement attribution; p95 retrieval < 500 ms | Not started |
| M5 | **Hindi & Hinglish** | Ask and get answers in Hindi / Hinglish; Hindi sources | Language match ≥ 98%; within 10% of English scores; policy evals pass in all languages; UI localized | Not started |
| M6 | **Go public** | Hosted, multi-user, secure, private, rights-clean launch | Rights gate green; no high security findings; 50 concurrent chats p95 first token < 3 s; data delete/export works; beta ≥ 20 users, ≥ 80% thumbs-up | Not started |

Update the **Status** column (Not started → Active → Done YYYY-MM-DD) when a
milestone starts or its exit gate is verified.

## 6. How to work from this roadmap

### 6.1 Picking up work

1. Open the **current milestone** (the one marked Active in §5).
2. Pick the lowest-numbered open step whose **Depends on** steps are done and
   whose GitHub issue is not labelled `blocked`.
3. Read the step here, its GitHub issue, and any linked spec. Follow
   [docs/standards/](standards/README.md).
4. If the step changes user-facing behavior and no spec exists, write or update
   `docs/specs/<feature>.md` first. The spec gate (`scripts/check_spec_gate.sh`)
   requires a `Spec: docs/specs/<file>.md` trailer (or `Spec-Exempt: <reason>`)
   on commits touching the feature surface.
5. For non-trivial steps: design → implementation plan → TDD implementation.
   Plans go under `docs/superpowers/plans/`.
6. Open a PR that references the step ID and says `Closes #<issue>`.
7. Tick the step's todos in its GitHub issue. Edit this file only when scope,
   order, decisions, or status change.

### 6.2 Conventions

- **Step IDs** (`M1.3`) are stable. Use them in issue titles
  (`[M1.3] …`), branch names (`feat/m1-3-guidance-policy`), commit scopes, and
  plan/spec filenames where helpful. Never renumber; if a step is dropped, mark
  it ~~struck through~~ with a reason.
- **New steps** discovered mid-milestone get the next free number in that
  milestone and a GitHub issue.
- **Eval gates that need a local LLM** (Ollama) cannot run in CI
  (`ASTRO_CI=1` stubs them). Run them locally before merge and record the
  result under `eval_reports/` and in the PR description.

### 6.3 Closing a milestone

A milestone closes only when **every exit-gate item is verified with
evidence** (eval numbers, test runs, links). Post the evidence on the
milestone's epic issue, set the milestone Done in §5, close the GitHub
milestone, then mark the next milestone Active and refine its todos
(rolling wave, D12) before starting work.

### 6.4 Changing the roadmap

Roadmap edits go through a PR like code. Reordering milestones or changing an
exit gate requires a decision-log entry (§4).

---

## 7. Milestones

Each step lists **Labels**, **Depends on**, **Todos**, and **Done when**.
Todos are the contract for the step's GitHub issue.

### M1 — MVP

**Goal:** make the existing system trustworthy and complete enough to use
daily: grounding bugs fixed, safe-but-useful guidance, the four planned
features live, saved profiles, and a backend API the future UI can build on.

#### M1.1 Repo hygiene

- **Labels:** `area:docs`, `type:chore`
- **Depends on:** —
- **Todos:**
  - [ ] Fix stale pre-refactor file paths in `docs/RAG_PLAN.md` and `docs/FUTURE_IMPROVEMENTS.md` (closes #6)
  - [ ] Add "historical — see ROADMAP.md" banner to `docs/AGENT_PROD_PLAN.md`
  - [ ] Annotate `docs/FUTURE_IMPROVEMENTS.md` and `docs/CORPUS_PATH.md` items that this roadmap absorbs with their step IDs
  - [ ] Remove leftover Chroma references in docs/README (e.g. "index is written to `chroma_db/`")
- **Done when:** #6 closed; no doc references removed modules or Chroma.

#### M1.2 Grounding integrity

- **Labels:** `area:rag`, `area:agent`, `type:bug`
- **Depends on:** —
- **Todos:**
  - [ ] Agent loop applies the citation-integrity backstop even when `rag_search` was never called (closes #2)
  - [ ] Tests for `[ref:…]` citation stripping in the agent loop and RAG-enriched consultation path (closes #3)
  - [ ] Unit tests for retrieval / rerank logic in `astro_agent/rag/search.py` (closes #4)
  - [ ] Humanizer rewrite no longer bypasses faithfulness checks: re-validate citations / grounding on the text users actually see, or constrain the humanizer so it cannot add claims (closes #5)
  - [ ] Re-run career eval; record result
- **Done when:** #2–#5 closed; career eval `rag_judge_grounding_avg` does not regress vs last accepted record.

#### M1.3 Guidance policy spec + two-sided eval

- **Labels:** `area:safety`, `area:evals`, `type:spec`
- **Depends on:** —
- **Policy (D11):**

  | Topic | Do | Don't |
  |-------|----|-------|
  | Health | Full astrological reading: 6th/8th houses, afflicted planets, body areas, vulnerable dasha/transit windows, classical citations | State a medical diagnosis as fact; advise stopping or replacing treatment. Add one line suggesting a doctor when symptoms are mentioned |
  | Longevity | Classical longevity category (alpa / madhya / purna ayu), maraka periods, health-sensitive windows, cited | Give a specific date or age of death |
  | Remedies | Recommend fully: mantra, gemstone, charity, puja, fasting, yantra — grounded and cited | Exaggerate danger to push a remedy. Always include low-cost options; warn when a gemstone would strengthen a malefic |
  | Legal / money | Astrological timing and favourable periods for cases, investments, property | Present itself as legal or financial advice |
  | Crisis | **Hard rule:** suicidal ideation or self-harm → empathetic response + helpline (India: Tele-MANAS 14416), normal reading paused | — |

- **Todos:**
  - [ ] Write `docs/specs/guidance-policy.md` (the table above, examples, tone guide); add to specs index
  - [ ] Implement policy in prompt builders (shared policy block, one source of truth)
  - [ ] Rule-based post-check for must-not patterns (death date/age, diagnosis-as-fact, stop-medication)
  - [ ] Crisis detection path that short-circuits to the crisis response
  - [ ] Golden set `data/golden/guidance_policy_v0.json`: ≥ 30 must-answer cases (health, longevity, remedies, legal/money timing) and ≥ 20 must-not cases
  - [ ] `evals/evaluate_guidance_policy.py`: rules + LLM judge; must-answer fails on refusal or empty hedging
- **Done when:** must-not cases pass 100%; must-answer answered substantively ≥ 95%.

#### M1.4 Manglik detection live

- **Labels:** `area:chart`, `area:rag`, `type:feature`
- **Depends on:** M1.3
- **Todos:**
  - [ ] Review and finalize `docs/specs/manglik-detection.md` (houses counted from lagna / Moon / Venus, cancellation rules, which rules are classical vs popular)
  - [ ] Deterministic `manglik` computation in `astro_agent/chart/` with tests on known charts
  - [ ] Intent/entity vocabulary for Manglik / Kuja / Mangal dosha
  - [ ] Agent tool + prompt section; cite BPHS where it supports the reading
  - [ ] ≥ 8 golden cases (retrieval + answer)
  - [ ] Mark spec **live**
- **Done when:** spec live; golden cases pass.

#### M1.5 Sade Sati / Dhaiya live

- **Labels:** `area:chart`, `area:rag`, `type:feature`
- **Depends on:** M1.3
- **Todos:**
  - [ ] Review and finalize `docs/specs/sade-sati.md`
  - [ ] Saturn transit computation relative to natal Moon: Sade Sati (12th/1st/2nd from Moon, with phase), Dhaiya (4th/8th); start/end dates
  - [ ] Tests against reference dates for known charts
  - [ ] Agent tool + prompt section; ≥ 8 golden cases
  - [ ] Mark spec **live**
- **Done when:** spec live; dates match reference within one day; golden cases pass.

#### M1.6 Guna Milan matching live

- **Labels:** `area:chart`, `area:api`, `type:feature`
- **Depends on:** M1.3, M1.8
- **Todos:**
  - [ ] Review and finalize `docs/specs/guna-milan-matching.md`
  - [ ] Ashtakoot scoring (Varna 1, Vashya 2, Tara 3, Yoni 4, Graha Maitri 5, Gana 6, Bhakoot 7, Nadi 8 = 36) with dosha cancellation rules
  - [ ] Two-profile input path (service + API)
  - [ ] Tests against reference scores for known pairs
  - [ ] Prompt section; ≥ 8 golden cases
  - [ ] Mark spec **live**
- **Done when:** spec live; scores match reference; golden cases pass.

#### M1.7 Remedies live

- **Labels:** `area:rag`, `area:safety`, `type:feature`
- **Depends on:** M1.3
- **Todos:**
  - [ ] Review and finalize `docs/specs/remedies.md` against the guidance policy
  - [ ] Remedies as a cross-cutting answer section in every domain prompt
  - [ ] Gemstone safety logic (functional malefic check) in deterministic code
  - [ ] Retrieval vocabulary for remedy terms; cite BPHS remedial chapters
  - [ ] ≥ 10 golden cases incl. "should I wear X?"
  - [ ] Mark spec **live**
- **Done when:** spec live; golden cases pass; guidance-policy eval still green.

#### M1.8 Birth profiles & conversation persistence

- **Labels:** `area:api`, `area:storage`, `type:feature`
- **Depends on:** —
- **Todos:**
  - [ ] SQLAlchemy + Alembic setup with SQLite (D6); tables: `profiles`, `conversations`, `messages`
  - [ ] Repository interfaces (no SQL outside the storage package)
  - [ ] Birth-time certainty field (`exact` / `approximate` / `unknown`); agent flags lagna- and house-sensitive claims when time is uncertain
  - [ ] Multi-turn memory loaded from stored messages; summarisation of long chats; test over a 20-turn conversation
- **Done when:** profiles and chats survive restart; uncertainty handling covered by tests.

#### M1.9 Backend API (FastAPI)

- **Labels:** `area:api`, `type:feature`
- **Depends on:** M1.8
- **Todos:**
  - [ ] Define `AgentRunner` protocol: `run(request) -> Iterator[AgentEvent]`; event types `status`, `tool_call`, `token`, `citation`, `final`, `error`, and reserved `clarification`
  - [ ] Wrap the current loop / `run_consultation` behind `AgentRunner`
  - [ ] FastAPI app: profiles CRUD, conversations list/get, `POST /chat` streaming via SSE
  - [ ] OpenAPI schema published; dev command (`uvicorn`) and devcontainer port
  - [ ] API tests with `TestClient` (LLM mocked)
  - [ ] Streamlit switched to call the API over HTTP only
- **Done when:** Streamlit has no direct imports of `astro_agent.service`; API tests green.

#### M1.10 MVP eval gates

- **Labels:** `area:evals`, `type:chore`
- **Depends on:** M1.4–M1.7
- **Todos:**
  - [ ] Dosha/matching/remedy golden set (`data/golden/dosha_v0.json`) consolidating M1.4–M1.7 cases; schema-validated
  - [ ] Re-add deferred dosha/remedy questions to real-world set where now supported
  - [ ] Document the local pre-merge eval checklist (which evals, thresholds) in `docs/standards/testing.md`
  - [ ] CI: schema validation of all golden files
- **Done when:** thresholds documented; all MVP gates measurable with one command each.

**M1 exit gate**

- [ ] Issues #2–#6 closed
- [ ] Manglik, Sade Sati, Guna Milan, Remedies specs marked **live**
- [ ] RAG golden set (`rag_eval_v0`) gold@3 ≥ 1.00
- [ ] Dosha golden set retrieval@3 ≥ 0.8
- [ ] Guidance policy: must-not 100%, must-answer ≥ 95%
- [ ] Streamlit runs only through the API

---

### M2 — Foundation & knowledge

**Goal:** the platform and knowledge layer everything later builds on —
swappable models, LangGraph agent, multi-book ingest, structured astrology
knowledge, complete chart math, a self-checking agent, storage, observability.

#### M2.1 Model provider abstraction

- **Labels:** `area:llm`, `type:feature` · **Depends on:** M1
- **Todos:** `LLMProvider` interface (generate, chat with tools, structured output, streaming); Ollama and Claude implementations; tool-call format adapter; provider/model selected by config; eval runner accepts `--provider`; quality/latency/cost comparison report.
- **Done when:** switching provider is config-only; evals pass on Ollama and one cloud model.

#### M2.2 Storage layer

- **Labels:** `area:storage`, `type:feature` · **Depends on:** M1.8
- **Todos:** extend repositories with `feedback` and audit fields; Postgres-compatible schema (tested against Postgres in a container); migration discipline documented; backup/export of local DB.
- **Done when:** test suite runs against SQLite and Postgres.

#### M2.3 LangGraph migration

- **Labels:** `area:agent`, `type:feature` · **Depends on:** M2.1, M2.2
- **Scope (D4):** LangGraph runs the agent graph; model calls, retrieval, and chart math stay our own code.
- **Todos:** design spec for the graph (nodes: classify → chart → retrieve → reason → verify → answer); port current loop with parity; SQLite checkpointer (shared DB); interrupt support for clarifying questions; map LangGraph events onto the `AgentRunner` event contract (API/UI untouched); remove the custom loop after parity.
- **Done when:** all evals ≥ pre-migration baseline; conversations resume after restart.

#### M2.4 Multi-book ingest pipeline

- **Labels:** `area:corpus`, `area:rag`, `type:feature` · **Depends on:** M1
- **Todos:** `data/corpus/<book>/manifest.json` schema (book id, title, author, translator, edition, language, tradition, licence status per D10, source, chapter→topic maps) replacing BPHS-only hardcoding; ingest CLI `--book <id>`, idempotent; chunk metadata (book, chapter, verse, topic tags); per-book citation prefix + allowlist; `book` filter in search; ingest QA report (OCR confidence, chunk counts, spot-check sample); per-book golden-set template. Absorbs `docs/CORPUS_PATH.md` remaining work.
- **Done when:** BPHS Vol 1 re-ingested through the new pipeline with no eval regression.

#### M2.5 Embedding model evaluation

- **Labels:** `area:rag`, `area:i18n`, `type:spike` · **Depends on:** M2.4
- **Todos:** benchmark multilingual candidates (e.g. `bge-m3`, `multilingual-e5`) vs `nomic-embed-text` on all golden sets plus a small Hindi/Hinglish probe set; latency and index size; decision recorded in §4; documented re-index procedure.
- **Done when:** decision logged; if switching, re-indexed with no regression.

#### M2.6 Structured knowledge base

- **Labels:** `area:knowledge`, `type:feature` · **Depends on:** M1
- **Todos:** pydantic-validated YAML under `data/knowledge/`: planets (karakatvas, dignities, friendships, aspects), signs, houses (significations), nakshatras (lord, deity, padas), yogas (definitions + conditions), each entry with source citation; loader + lookup API; `lookup_knowledge` tool; use for query expansion in retrieval.
- **Done when:** schema-validated in CI; tool covered by tests; retrieval evals not regressed.

#### M2.7 Chart engine completeness

- **Labels:** `area:chart`, `type:feature` · **Depends on:** M1
- **Todos:** divisional charts (D9, D10, D7, D12, … full Shodashavarga); transits (gochar) with Moon-sign reference; ashtakavarga / sarvashtakavarga; shadbala; panchang (tithi, nakshatra, yoga, karana, vara); pratyantar dasha; reference-chart fixtures (≥ 20 charts) validated against established software (e.g. Jagannatha Hora).
- **Done when:** all calculations match reference fixtures.

#### M2.8 Agent capabilities

- **Labels:** `area:agent`, `type:feature` · **Depends on:** M2.3, M2.6, M2.7
- **Todos:** planner node for multi-part questions; new tools (`get_transits`, `get_divisional_chart`, `lookup_knowledge`, `get_panchang`, `compare_charts`); **verification node** that checks every chart claim in the draft against the computed chart and every citation against retrieved text, and repairs or rejects; clarifying-question interrupts (e.g. missing birth time).
- **Done when:** chart-fact contradiction eval shows 0 contradictions; multi-part question golden cases pass.

#### M2.9 Observability

- **Labels:** `area:infra`, `type:feature` · **Depends on:** M2.1
- **Todos:** request ID propagated through API → graph → tools → provider; per-request latency, tokens, cost by provider; extend `astro_agent/utils/tracer.py` and summary scripts; eval trend report over `eval_reports/`.
- **Done when:** one command shows latency/cost and eval trends.

#### M2.10 Pilot book: BPHS Vol 2

- **Labels:** `area:corpus`, `type:feature` · **Depends on:** M2.4, M2.5
- **Todos:** run the full per-book pipeline on BPHS Vol 2 (manifest, OCR/clean, ingest, QA report, ≥ 15-question golden set); fix pipeline gaps found; write the per-book runbook draft used in M4.
- **Done when:** BPHS Vol 2 retrieval@3 ≥ 0.8; Vol 1 not regressed.

**M2 exit gate**

- [ ] Provider swap is config-only; evals pass on Ollama and one cloud model
- [ ] LangGraph migration evals ≥ baseline
- [ ] BPHS Vol 2 pilot ≥ 0.8 retrieval@3
- [ ] Chart calculations match reference on ≥ 20 charts
- [ ] 0 chart-fact contradictions on the eval set

---

### M3 — Beautiful chat UI

**Goal:** a polished, mobile-ready Next.js product UI on top of the API.
Visual design is decided in M3.1's spec.

#### M3.1 Design system & UX spec

- **Labels:** `area:ui`, `type:spec` · **Depends on:** M2
- **Todos:** `docs/specs/chat-ui.md` with wireframes; visual direction (Vedic-inspired, modern); design tokens; shadcn/ui + Tailwind setup; light/dark; mobile-first; WCAG AA.

#### M3.2 App shell

- **Labels:** `area:ui`, `type:feature` · **Depends on:** M3.1
- **Todos:** Next.js + TypeScript app (`web/`); typed API client generated from FastAPI OpenAPI; single local user with auth seam for M6; frontend lint/typecheck in CI.

#### M3.3 Chat core

- **Labels:** `area:ui`, `type:feature` · **Depends on:** M3.2
- **Todos:** token streaming via SSE; step indicators from events ("Calculating your chart…"); markdown rendering; stop / regenerate / edit-and-resend; copy; suggested follow-ups; starter prompts per life area; clarifying-question UI for agent interrupts.

#### M3.4 Grounding UX

- **Labels:** `area:ui`, `area:rag`, `type:feature` · **Depends on:** M3.3
- **Todos:** citation chips → side panel with verse text, book, chapter; "Why this answer" (chart factors used); confidence indicator.

#### M3.5 Chart visuals

- **Labels:** `area:ui`, `area:chart`, `type:feature` · **Depends on:** M3.2
- **Todos:** North and South Indian chart SVG components; divisional chart switcher; dasha timeline; transit view.

#### M3.6 Profiles & matching flow

- **Labels:** `area:ui`, `type:feature` · **Depends on:** M3.2
- **Todos:** onboarding (birth details, city autocomplete, birth-time certainty); multiple profiles (family); switch profile mid-chat; two-profile Guna Milan flow.

#### M3.7 Conversations & export

- **Labels:** `area:ui`, `type:feature` · **Depends on:** M3.3
- **Todos:** history sidebar; search, rename, delete, pin; export a reading to PDF / Markdown report.

#### M3.8 "Today for you" daily guidance

- **Labels:** `area:ui`, `area:chart`, `type:feature` · **Depends on:** M3.2
- **Todos:** spec `docs/specs/daily-guidance.md`; backend endpoint combining transits, panchang, and active dasha; daily card UI; golden cases for daily guidance quality.

#### M3.9 Feedback loop

- **Labels:** `area:ui`, `area:evals`, `type:feature` · **Depends on:** M3.3
- **Todos:** thumbs up/down with reason; stored via M2.2; script to harvest candidates into golden sets (FUTURE_IMPROVEMENTS §3.2).

#### M3.10 Frontend quality

- **Labels:** `area:ui`, `type:chore` · **Depends on:** M3.3
- **Todos:** Playwright end-to-end suite (onboarding, chat, citation, profile switch, matching); Lighthouse budget checks; frontend CI job.

**M3 exit gate**

- [ ] Every M1 and M2 capability usable from the new UI
- [ ] Playwright suite green in CI
- [ ] Lighthouse mobile accessibility ≥ 90 and performance ≥ 90
- [ ] First streamed event ≤ 1 s after send
- [ ] Owner completes 5 scripted tasks (onboard, ask, open citation, switch profile, match) unaided

---

### M4 — Classical library

**Goal:** ingest every pioneer book on Hindu astrology, with per-book quality
gates and answers that reason across books honestly.

#### M4.1 Book register

- **Labels:** `area:corpus`, `type:chore` · **Depends on:** M2.10
- **Todos:** `docs/corpus/BOOKS.md` listing title, author, edition owned, licence status, tier, tradition, ingest status. Proposed tiers (adjust at kickoff):
  - **Tier 1 — Parashari core:** BPHS Vol 2 (done in M2.10), Brihat Jataka, Saravali, Phaladeepika, Jataka Parijata, Uttara Kalamrita, Laghu Parashari
  - **Tier 2 — specialised:** Jaimini Sutras, Prasna Marga, Muhurta Chintamani, Hora Sara, Sarvartha Chintamani, Chamatkar Chintamani, Bhavartha Ratnakara, Brihat Samhita
  - **Tier 3 — popular / modern (optional):** Lal Kitab; modern authorities (e.g. B.V. Raman) — copyrighted, personal use only

#### M4.2 Per-book runbook & tooling

- **Labels:** `area:corpus`, `area:docs`, `type:chore` · **Depends on:** M4.1
- **Todos:** finalize runbook from M2.10 (acquire legal copy → OCR/extract → clean → chapter/verse map → manifest → ingest → QA report → ≥ 15-question golden set → eval gate → enable); issue template for per-book work.

#### M4.3 Tier 1 ingestion

- **Labels:** `area:corpus`, `type:feature` · **Depends on:** M4.2
- **Todos:** one sub-issue per Tier 1 book, created at M4 kickoff, each following the runbook.

#### M4.4 Tier 2 ingestion

- **Labels:** `area:corpus`, `type:feature` · **Depends on:** M4.2
- **Todos:** one sub-issue per Tier 2 book, created at M4 kickoff. Ingesting Prasna Marga and Muhurta Chintamani makes them searchable only; horary and muhurta *features* are M4.8 decisions.

#### M4.5 Multi-book retrieval quality

- **Labels:** `area:rag`, `type:feature` · **Depends on:** M4.3
- **Todos:** source-diversity rerank; dedupe of parallel verses across texts; disagreement handling — when texts differ, present both with attribution ("Parashara says X; Mantreswara says Y"); golden disagreement cases.

#### M4.6 Tradition awareness

- **Labels:** `area:rag`, `area:llm`, `type:feature` · **Depends on:** M4.3
- **Todos:** tradition metadata (Parashari, Jaimini, Kerala, Lal Kitab) used in prompts; Lal Kitab and Jaimini content always labelled, never blended silently into Parashari reasoning.

#### M4.7 Scale & book toggles

- **Labels:** `area:rag`, `area:infra`, `type:feature` · **Depends on:** M4.3
- **Todos:** p95 retrieval < 500 ms at 20k+ chunks; incremental re-index; per-book enable/disable flag (reused by the M6.1 rights gate).

#### M4.8 New-book feature specs

- **Labels:** `area:chart`, `type:spec` · **Depends on:** M4.4
- **Todos:** decide and spec (each separately): Jaimini chara dasha + chara karakas; muhurta (auspicious timing) tool; Kaal Sarp and Pitru dosha (deferred in FUTURE_IMPROVEMENTS §1.1); horary (Prashna) go/no-go.

#### M4.9 Eval consolidation

- **Labels:** `area:evals`, `type:chore` · **Depends on:** M4.5
- **Todos:** cross-book golden set; `real_world_questions_v1.json`; per-book scores in one report.

#### M4.10 Tier 3 books (optional)

- **Labels:** `area:corpus`, `type:feature` · **Depends on:** M4.6
- **Todos:** Lal Kitab and selected modern authorities, labelled by tradition, licence recorded.

**M4 exit gate**

- [ ] All Tier 1 and Tier 2 books ingested with manifest and licence status
- [ ] Each book's golden set retrieval@3 ≥ 0.8
- [ ] Overall RAG gold@3 not regressed
- [ ] Disagreement cases answered with per-book attribution
- [ ] p95 retrieval latency < 500 ms

---

### M5 — Hindi & Hinglish

**Goal:** users can ask in English, Hindi (Devanagari), or Hinglish (romanized
Hindi) and get answers in the same language, grounded in English and Hindi
sources.

#### M5.1 Language detection & response policy

- **Labels:** `area:i18n`, `type:feature` · **Depends on:** M4
- **Todos:** detect en / hi / Hinglish; reply in the same language; per-profile override.

#### M5.2 Bilingual glossary

- **Labels:** `area:i18n`, `area:knowledge`, `type:feature` · **Depends on:** M5.1
- **Todos:** Sanskrit / Hindi / Hinglish spelling variants ("shani", "sade saati", "mangal dosh") in the knowledge base; intent router and entity extraction use them.

#### M5.3 Cross-lingual retrieval

- **Labels:** `area:i18n`, `area:rag`, `type:feature` · **Depends on:** M5.2
- **Todos:** Hindi/Hinglish queries retrieve English sources via multilingual embeddings (M2.5); query-translation fallback; eval.

#### M5.4 Hindi-language books

- **Labels:** `area:i18n`, `area:corpus`, `type:feature` · **Depends on:** M5.3
- **Todos:** Devanagari OCR quality pass; ingest Hindi editions/commentaries through the per-book runbook.

#### M5.5 Hindi generation quality

- **Labels:** `area:i18n`, `area:llm`, `type:feature` · **Depends on:** M5.1
- **Todos:** measure local model Hindi quality; route Hindi to a cloud model if needed (via M2.1); adapt humanizer for Hindi.

#### M5.6 UI localization

- **Labels:** `area:i18n`, `area:ui`, `type:feature` · **Depends on:** M5.1
- **Todos:** i18n framework in `web/`; Hindi UI strings; Devanagari fonts; localized dates.

#### M5.7 Multilingual evals

- **Labels:** `area:i18n`, `area:evals`, `type:feature` · **Depends on:** M5.3
- **Todos:** Hindi and Hinglish golden sets (translated + native questions); language-match rate metric; guidance-policy eval in all three languages.

**M5 exit gate**

- [ ] Reply language matches question language ≥ 98%
- [ ] Hindi and Hinglish retrieval and grounding scores within 10% of English
- [ ] Guidance-policy evals pass in all three languages
- [ ] UI fully localized

---

### M6 — Go public

**Goal:** a hosted, multi-user, secure, private, rights-clean launch.

#### M6.1 Book rights gate

- **Labels:** `area:corpus`, `area:infra`, `type:feature` · **Depends on:** M4.7
- **Todos:** CI check fails if any book enabled for the public deployment is not `public-domain` or `licensed`; non-cleared books disabled in public config; licence evidence recorded per book.

#### M6.2 Accounts & data rights

- **Labels:** `area:api`, `area:ui`, `type:feature` · **Depends on:** M3
- **Todos:** sign-in (email OTP or Google); per-user data isolation; user data export and account deletion.

#### M6.3 Infrastructure

- **Labels:** `area:infra`, `type:feature` · **Depends on:** M6.2
- **Todos:** spec choosing hosting provider; Docker images; Postgres + Qdrant server; staging + production; CD pipeline; secrets management; backups and restore drill.

#### M6.4 Cloud model in production

- **Labels:** `area:llm`, `area:infra`, `type:feature` · **Depends on:** M6.3
- **Todos:** choose provider from M2.1 eval matrix; fallback provider; per-user rate limits and quotas; prompt caching; cost dashboard and alerts.

#### M6.5 Privacy

- **Labels:** `area:safety`, `area:infra`, `type:feature` · **Depends on:** M6.2
- **Todos:** birth data treated as personal data (India DPDP Act; GDPR if EU users); consent + privacy policy; encryption at rest; retention policy; PII review of logs (`interactions.jsonl`, traces).

#### M6.6 Security

- **Labels:** `area:safety`, `area:infra`, `type:feature` · **Depends on:** M6.3
- **Todos:** OWASP review; prompt-injection hardening for user input and ingested text; abuse limits; dependency scanning in CI.

#### M6.7 Production observability & online quality

- **Labels:** `area:infra`, `area:evals`, `type:feature` · **Depends on:** M6.3
- **Todos:** error tracking; uptime and latency alerts; sampled conversations scored by an automated judge; feedback dashboard.

#### M6.8 Legal pages

- **Labels:** `area:docs`, `type:chore` · **Depends on:** M6.5
- **Todos:** terms of service; "astrology is guidance" disclaimer; age policy.

#### M6.9 Billing (optional)

- **Labels:** `area:api`, `type:spec` · **Depends on:** M6.2
- **Todos:** separate spec; free tier + subscription (Razorpay / Stripe). Not required for launch.

#### M6.10 Beta & launch

- **Labels:** `area:infra`, `type:chore` · **Depends on:** M6.1–M6.8
- **Todos:** closed beta (≥ 20 users); feedback triage; load test; public launch checklist.

**M6 exit gate**

- [ ] Rights gate green
- [ ] Security review: no high-severity findings open
- [ ] Load test: 50 concurrent chats, p95 time to first token < 3 s
- [ ] User data deletion and export verified
- [ ] Beta ≥ 20 users with ≥ 80% thumbs-up

---

## 8. GitHub mapping

| Roadmap | GitHub |
|---------|--------|
| Milestone `M1`–`M6` | GitHub **Milestone** (description = goal + exit gate) |
| Milestone | One **epic issue** `[M1] MVP — epic` with the exit gate as a checklist |
| Step `M1.3` | **Sub-issue** of the epic, titled `[M1.3] <step title>`, with todos, done-when, depends-on |
| Existing issues #2–#6 | Attached to M1 as sub-issues of the M1 epic and referenced by M1.1 / M1.2 |
| Per-book work (M4.3, M4.4) | Sub-issues created at M4 kickoff |
| Labels | `area:{rag,chart,agent,api,ui,corpus,evals,infra,i18n,safety,docs,llm,storage,knowledge}`, `type:{epic,feature,bug,chore,spec,spike}`, `blocked` |
| Board | GitHub Project "Astro AI Roadmap" (if available) |

The GitHub issues are generated from this file; when they diverge, **this
file wins** for scope and order, and the issue wins for todo progress.

## 9. Out of scope (parking lot)

Tracked in [FUTURE_IMPROVEMENTS.md §5](FUTURE_IMPROVEMENTS.md); not planned in
M1–M6 unless promoted via a decision-log entry: KP system, Nadi astrology,
Western astrology, regional languages beyond Hindi (Tamil, Telugu, Kannada),
voice input, native mobile apps.

## 10. Roadmap changelog

| Date | Change |
|------|--------|
| 2026-10-20 | Initial roadmap (M1–M6, decisions D1–D12) |
