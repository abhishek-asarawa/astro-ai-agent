"""RAG retrieval evaluation harness (Phase 4 v0).

Reads a golden dataset of (question, gold_citations, silver_citations)
cases, runs each through `rag_search.search_for_eval`, and scores three metrics.

Optional **Tier 3** path: ``--judge-model`` generates a RAG-grounded answer per case
(using the same retrieved top-``RERANK_TOP_K`` chunks as production) and runs the shared
JSON faithfulness judge from ``eval_grounding``; metrics are diagnostic only (retention
still uses gold@3, silver@5, heuristic delta + ``outcomes_checksum``).

By default the retriever intent matches production: `intent_router.detect_intent(question)`.
Pass ``golden_intent=True`` (CLI: ``--golden-intent``) to use the golden file's
``expected_intent`` only and isolate the retriever from routing.

- `rag_recall_at_3_gold`: fraction of cases where any gold ref_id is in
  the post-rerank top-3.
- `rag_recall_at_5_silver`: fraction of cases where any silver ref_id is
  in the post-rerank top-5.
- `rag_heuristic_delta`: mean rank improvement for gold refs that
  appeared in the pre-rerank top-`DENSE_TOP_K`. Positive means the
  reranker pulled gold refs closer to the top.

Results are persisted with smart retention in `rag_eval_history.json`
(separate from career eval history).

Retention compares runs **lexicographically** on
`(rag_recall_at_3_gold, rag_recall_at_5_silver, rag_heuristic_delta)`.
If that tuple **strictly improves**, the run is accepted. If it **regresses**,
the run is rejected. If it **ties**, we compare **`outcomes_checksum`** (SHA-256
over canonical per-case outcomes: booleans, deltas, post/pre top-5 ref_ids). A
changed checksum means per-case retrieval changed even when headline metrics
match. If summary **and** checksum match the baseline (or baseline predates
checksums), the run is still accepted so the rolling history can refresh the
snapshot (eviction picks the weakest tier, then oldest among ties).
"""

import argparse
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from statistics import mean

import rag_config as cfg
from astro_engine import (
    append_classical_references_block,
    build_prompt_for_intent,
    query_ollama_once,
    resolve_ollama_config,
)
from eval_grounding import run_grounding_judge, score_grounding_embedding
from intent_router import detect_intent
from rag_search import search_for_eval


DEFAULT_GOLDEN_PATH = "data/golden/rag_eval_v0.json"
DEFAULT_REPORT_PATH = "rag_eval_report.json"
DEFAULT_HISTORY_PATH = "rag_eval_history.json"
DEFAULT_RECORDS_DIR = "rag_eval_records"
EVAL_TYPE = "rag_v0"
MAX_HISTORY_RECORDS = 3
# Stored JSON only; full answer is still sent to the judge.
MODEL_ANSWER_JSON_MAX_CHARS = 2000


def load_golden(path):
    cases = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(cases, list):
        raise ValueError(f"Golden file {path} must contain a JSON array of cases.")
    return cases


def _rank_of(ref_id, ordered_ref_ids):
    try:
        return ordered_ref_ids.index(ref_id)
    except ValueError:
        return -1


def _gold_in_top_k(gold_refs, ordered, k):
    top = set(ordered[:k])
    return any(ref in top for ref in gold_refs)


def _heuristic_delta_for_case(gold_refs, pre_order, post_order, dense_top_k):
    """Mean (pre_rank - post_rank) for gold refs found in pre-rerank top-K."""
    deltas = []
    pre_horizon = set(pre_order[:dense_top_k])
    for ref in gold_refs:
        if ref not in pre_horizon:
            continue
        pre = _rank_of(ref, pre_order)
        post = _rank_of(ref, post_order)
        if pre == -1 or post == -1:
            continue
        deltas.append(pre - post)
    if not deltas:
        return None
    return round(mean(deltas), 3)


def _compact_intent_detection(info):
    """Serialize detect_intent() for JSON (rule_scores keys are str-safe)."""
    if not info:
        return None
    out = {
        "intent": info.get("intent"),
        "method": info.get("method"),
        "confidence": info.get("confidence"),
    }
    rs = info.get("rule_scores")
    if isinstance(rs, dict):
        out["rule_scores"] = rs
    return out


def chart_context_to_minimal_features(chart_context):
    """Map golden ``chart_context`` into the structure ``build_prompt_for_intent`` expects.

    House lordships and dashas are empty so domain prompts still render; judge focuses on
    classical claims vs retrieved chunks, not full-chart fidelity.
    """
    ctx = chart_context or {}
    lagna = ctx.get("lagna", "Unknown")
    if not isinstance(lagna, str):
        lagna = str(lagna)
    planets = {}
    dignities = {}
    active_antardasha = {}
    antar_lord = ctx.get("_antardasha_lord")
    if isinstance(antar_lord, str) and antar_lord.strip():
        active_antardasha = {"dasha": antar_lord.strip()}

    for key, payload in ctx.items():
        if key in ("lagna", "_antardasha_lord") or not isinstance(payload, dict):
            continue
        pname = (key[:1].upper() + key[1:].lower()) if key else key
        sign = payload.get("sign") or payload.get("rashi") or "Unknown"
        planets[pname] = {
            "rashi": sign,
            "degrees": 0.0,
            "nakshatra": "N/A",
        }
        dig = payload.get("dignity")
        if dig:
            ds = str(dig).strip()
            if not ds.startswith("["):
                ds = f"[{ds}]"
            dignities[pname] = ds
    return {
        "lagna": {"rashi": lagna, "degrees": 0.0, "nakshatra": "N/A"},
        "planets": planets,
        "planetary_dignities": dignities,
        "house_lordships": {},
        "dasha_timeline": [],
        "active_dasha": {},
        "next_dasha": {},
        "active_antardasha": active_antardasha,
    }


def evaluate_case(
    case,
    db_path,
    *,
    golden_intent,
    intent_model,
    intent_timeout_s,
    intent_num_ctx,
    judge_model=None,
    judge_eligible=False,
    answer_model=None,
    answer_timeout_s=120,
    answer_num_ctx=None,
    judge_timeout_s=90,
    judge_num_ctx=8192,
    rag_grounding=True,
):
    question = case["question"]
    expected_intent = case.get("expected_intent", "general")
    chart_facts = case.get("chart_context")
    gold_refs = case.get("gold_citations", []) or []
    silver_refs = case.get("silver_citations", []) or []

    intent_detection = None
    intent_matches_golden = None
    if golden_intent:
        used_intent = expected_intent
    else:
        info = detect_intent(
            question,
            model_name=intent_model,
            timeout_s=intent_timeout_s,
            num_ctx=intent_num_ctx,
        )
        intent_detection = _compact_intent_detection(info)
        used_intent = (info or {}).get("intent", "general")
        intent_matches_golden = used_intent == expected_intent

    chunks, pre_order = search_for_eval(
        question=question,
        intent=used_intent,
        chart_facts=chart_facts,
        db_path=db_path,
    )

    post_order = [c.ref_id for c in chunks]

    gold_in_top_3 = _gold_in_top_k(gold_refs, post_order, cfg.RERANK_TOP_K) if gold_refs else False
    silver_in_top_5 = _gold_in_top_k(silver_refs, post_order, cfg.SILVER_TOP_K) if silver_refs else False

    delta = _heuristic_delta_for_case(
        gold_refs=gold_refs,
        pre_order=pre_order,
        post_order=post_order,
        dense_top_k=cfg.DENSE_TOP_K,
    )

    top_5_view = [
        {
            "rank": c.post_rerank_rank,
            "ref_id": c.ref_id,
            "score": round(c.score, 4),
            "similarity": round(c.similarity, 4),
            "pre_rerank_rank": c.pre_rerank_rank,
            "matched_entities": c.matched_entities,
            "token_count": c.metadata.get("token_count"),
            "verse_start": c.metadata.get("verse_start"),
            "verse_end": c.metadata.get("verse_end"),
        }
        for c in chunks[:cfg.SILVER_TOP_K]
    ]

    row = {
        "case_id": case.get("case_id", "unknown"),
        "question": question,
        "expected_intent": expected_intent,
        "used_intent": used_intent,
        "intent_detection": intent_detection,
        "intent_matches_golden": intent_matches_golden,
        "gold_citations": gold_refs,
        "silver_citations": silver_refs,
        "gold_in_top_3": gold_in_top_3,
        "silver_in_top_5": silver_in_top_5,
        "heuristic_delta": delta,
        "post_rerank_top_5": top_5_view,
        "pre_rerank_top_5": pre_order[:cfg.SILVER_TOP_K],
    }

    if judge_model and not judge_eligible:
        row["llm_judge_skipped"] = True
        return row

    if judge_model and judge_eligible:
        row["rag_active"] = False
        row["grounding_max_sim"] = None
        row["grounding_mean_sim"] = None
        row["grounding_error"] = None
        row["judge_grounding"] = None
        row["judge_supported_ratio"] = None
        row["judge_note"] = ""
        row["judge_error"] = None
        row["model_answer"] = None
        row["answer_error"] = None

        chunks_for_prompt = chunks[: cfg.RERANK_TOP_K]
        if not chunks_for_prompt:
            print(f"[judge] skipping case {row['case_id']}: no chunks retrieved", flush=True)
            row["judge_error"] = "no_chunks"
            return row

        features = chart_context_to_minimal_features(chart_facts)
        base_prompt = build_prompt_for_intent(features, question, used_intent)
        enriched_prompt, allowed_refs, included, rag_active = append_classical_references_block(
            base_prompt, chunks_for_prompt, used_intent
        )
        row["rag_active"] = rag_active
        if not rag_active or not included:
            print(f"[judge] skipping case {row['case_id']}: no RAG block / included chunks", flush=True)
            row["judge_error"] = "no_chunks"
            return row

        try:
            response = query_ollama_once(
                enriched_prompt,
                temperature=0.2,
                timeout_s=answer_timeout_s,
                model_name=answer_model,
                allowed_refs=allowed_refs,
                num_ctx=answer_num_ctx,
            )
        except Exception as exc:
            row["answer_error"] = str(exc)
            response = ""

        row["model_answer"] = (response or "")[:MODEL_ANSWER_JSON_MAX_CHARS]

        if rag_grounding and included and allowed_refs:
            g = score_grounding_embedding(response, included)
            row["grounding_max_sim"] = g["grounding_max_sim"]
            row["grounding_mean_sim"] = g["grounding_mean_sim"]
            if g.get("grounding_error"):
                row["grounding_error"] = g["grounding_error"]
        elif not rag_grounding:
            row["grounding_max_sim"] = None
            row["grounding_mean_sim"] = None

        if judge_model and included and allowed_refs:
            j = run_grounding_judge(
                response,
                included,
                judge_model=judge_model,
                timeout_s=judge_timeout_s,
                num_ctx=judge_num_ctx,
            )
            row.update(
                {
                    "judge_grounding": j.get("judge_grounding"),
                    "judge_supported_ratio": j.get("judge_supported_ratio"),
                    "judge_note": j.get("judge_note"),
                    "judge_error": j.get("judge_error"),
                }
            )
            if j.get("judge_raw"):
                row["judge_raw"] = j["judge_raw"]

    return row


def evaluate(
    golden_path,
    db_path,
    *,
    golden_intent=False,
    intent_model=None,
    intent_timeout_s=45,
    intent_num_ctx=None,
    judge_model=None,
    max_judge_cases=None,
    answer_model=None,
    answer_timeout_s=120,
    answer_num_ctx=None,
    judge_timeout_s=90,
    judge_num_ctx=8192,
    rag_grounding=True,
):
    cases = load_golden(golden_path)
    if not cases:
        return {"summary": {}, "details": []}

    n_cases = len(cases)
    details = []
    for i, case in enumerate(cases):
        judge_eligible = bool(judge_model) and (max_judge_cases is None or i < max_judge_cases)
        if judge_model:
            print(
                f"[{i + 1}/{n_cases}] case={case.get('case_id', 'unknown')} "
                f"llm_judge={'on' if judge_eligible else 'skipped'}",
                flush=True,
            )
        details.append(
            evaluate_case(
                case,
                db_path,
                golden_intent=golden_intent,
                intent_model=intent_model,
                intent_timeout_s=intent_timeout_s,
                intent_num_ctx=intent_num_ctx,
                judge_model=judge_model,
                judge_eligible=judge_eligible,
                answer_model=answer_model,
                answer_timeout_s=answer_timeout_s,
                answer_num_ctx=answer_num_ctx,
                judge_timeout_s=judge_timeout_s,
                judge_num_ctx=judge_num_ctx,
                rag_grounding=rag_grounding,
            )
        )

    n = len(details)
    recall_3_gold = sum(1 for d in details if d["gold_in_top_3"]) / n
    recall_5_silver = sum(1 for d in details if d["silver_in_top_5"]) / n
    deltas = [d["heuristic_delta"] for d in details if d["heuristic_delta"] is not None]
    delta_avg = round(mean(deltas), 3) if deltas else None

    if golden_intent:
        intent_routing_agreement = None
    else:
        matches = [d for d in details if d["intent_matches_golden"] is not None]
        intent_routing_agreement = (
            round(sum(1 for d in matches if d["intent_matches_golden"]) / len(matches), 3)
            if matches
            else None
        )

    summary = {
        "eval_type": EVAL_TYPE,
        "cases": n,
        "embed_model": cfg.EMBED_MODEL,
        "golden_intent": golden_intent,
        "intent_num_ctx": intent_num_ctx,
        "intent_routing_agreement": intent_routing_agreement,
        "rag_recall_at_3_gold": round(recall_3_gold, 3),
        "rag_recall_at_5_silver": round(recall_5_silver, 3),
        "rag_heuristic_delta": delta_avg,
        "outcomes_checksum": _outcomes_checksum(details),
        "dense_top_k": cfg.DENSE_TOP_K,
        "rerank_top_k": cfg.RERANK_TOP_K,
        "cross_encoder_rerank": cfg.CROSS_ENCODER_RERANK_ENABLED,
        "cross_encoder_model": cfg.CROSS_ENCODER_MODEL,
        "cross_encoder_heuristic_blend": cfg.CROSS_ENCODER_HEURISTIC_BLEND,
        "reranker_weights": {
            "entity_weight": cfg.ENTITY_WEIGHT,
            "entity_match_cap": cfg.ENTITY_MATCH_CAP,
            "entity_tail_weight": cfg.ENTITY_TAIL_WEIGHT,
            "entity_tail_max": cfg.ENTITY_TAIL_MAX,
            "intent_weight": cfg.INTENT_WEIGHT,
            "pre_rerank_weight": cfg.PRE_RERANK_WEIGHT,
            "chapter_hint_weight": cfg.CHAPTER_HINT_WEIGHT,
            "navamsa_align_weight": cfg.NAVAMSA_ALIGN_WEIGHT,
            "bm25_similarity_cap": cfg.BM25_SIMILARITY_CAP,
            "length_penalty_per_100": cfg.LENGTH_PENALTY_PER_100,
            "length_penalty_threshold": cfg.LENGTH_PENALTY_THRESHOLD,
        },
    }

    if judge_model:
        summary["rag_judge_model"] = judge_model
        summary["rag_answer_model"] = answer_model
        summary["rag_llm_judge_serial"] = True
        if max_judge_cases is not None:
            summary["rag_max_judge_cases"] = max_judge_cases
        gmax_vals = [
            d["grounding_max_sim"]
            for d in details
            if d.get("grounding_max_sim") is not None
        ]
        gmean_vals = [
            d["grounding_mean_sim"]
            for d in details
            if d.get("grounding_mean_sim") is not None
        ]
        if gmax_vals:
            summary["rag_grounding_max_sim_avg"] = round(mean(gmax_vals), 4)
            summary["rag_grounding_mean_sim_avg"] = round(mean(gmean_vals), 4)
        judge_vals = [
            d["judge_grounding"] for d in details if d.get("judge_grounding") is not None
        ]
        if judge_vals:
            summary["rag_judge_grounding_avg"] = round(mean(judge_vals), 3)
        ratio_vals = [
            d["judge_supported_ratio"]
            for d in details
            if d.get("judge_supported_ratio") is not None
        ]
        if ratio_vals:
            summary["rag_judge_supported_ratio_avg"] = round(mean(ratio_vals), 3)
        if rag_grounding:
            summary["rag_grounding_embed_model"] = cfg.EMBED_MODEL

    return {"summary": summary, "details": details}


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _outcomes_checksum(details):
    """Stable hash of per-case retrieval outcomes (not raw scores in top-5)."""
    payload = []
    for d in sorted(details, key=lambda x: str(x.get("case_id", ""))):
        post_rows = d.get("post_rerank_top_5") or []
        top5 = [x.get("ref_id") for x in post_rows]
        pre5 = list(d.get("pre_rerank_top_5") or [])
        payload.append(
            {
                "case_id": d.get("case_id"),
                "gold_in_top_3": bool(d.get("gold_in_top_3")),
                "silver_in_top_5": bool(d.get("silver_in_top_5")),
                "heuristic_delta": d.get("heuristic_delta"),
                "post_top5_ref_ids": top5,
                "pre_top5_ref_ids": pre5,
            }
        )
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _rank_tuple(summary):
    """Lexicographic rank for baseline selection and regression checks."""
    if not summary:
        return (-1.0, -1.0, -1e9)
    return (
        _safe_float(summary.get("rag_recall_at_3_gold")),
        _safe_float(summary.get("rag_recall_at_5_silver")),
        _safe_float(summary.get("rag_heuristic_delta")),
    )


def load_history(history_path):
    path = Path(history_path)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Warning: could not read history at {history_path}: {exc}", flush=True)
        return []
    if isinstance(data, dict):
        records = data.get("records", [])
    elif isinstance(data, list):
        records = data
    else:
        records = []
    return records if isinstance(records, list) else []


def save_history(history_path, records):
    Path(history_path).write_text(
        json.dumps({"version": 1, "records": records}, indent=2),
        encoding="utf-8",
    )


def select_baseline(records):
    if not records:
        return None
    return max(records, key=lambda r: _rank_tuple(r.get("summary", {})))


def passes_guardrails(new_summary, baseline_record):
    if baseline_record is None:
        return True, "no past record found"

    base_summary = baseline_record.get("summary", {})
    t_new = _rank_tuple(new_summary)
    t_base = _rank_tuple(base_summary)

    if t_new > t_base:
        return True, f"accepted: lexicographic improvement {t_new} > {t_base}"

    if t_new < t_base:
        return False, f"rejected: regression vs baseline {t_new} < {t_base}"

    chk_new = new_summary.get("outcomes_checksum")
    chk_base = base_summary.get("outcomes_checksum")

    if chk_base is None:
        return True, "accepted: summary ties baseline; baseline has no outcomes_checksum (legacy)"

    if chk_new != chk_base:
        return True, "accepted: summary ties baseline; per-case outcomes differ (checksum)"

    return True, "accepted: summary and outcomes_checksum match baseline; rotating snapshot"


def apply_retention(records, new_record):
    eviction = None
    if len(records) < MAX_HISTORY_RECORDS:
        records.append(new_record)
        return records, eviction
    min_rank = min(_rank_tuple(r.get("summary", {})) for r in records)
    least_good = [
        r for r in records if _rank_tuple(r.get("summary", {})) == min_rank
    ]
    eviction = min(
        least_good,
        key=lambda r: (r.get("created_at", ""), r.get("record_id", "")),
    )
    records = [r for r in records if r.get("record_id") != eviction.get("record_id")]
    records.append(new_record)
    return records, eviction


def persist_accepted_report(records_dir, record_id, report):
    out_dir = Path(records_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"{record_id}.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return str(report_path)


def maybe_save_result(report, output_path, history_path):
    records = load_history(history_path)
    baseline = select_baseline(records)
    accepted, reason = passes_guardrails(report["summary"], baseline)

    if baseline is None:
        print("Decision: accept run because no past record exists.", flush=True)
    else:
        base_summary = baseline.get("summary", {})
        bt = _rank_tuple(base_summary)
        print(
            f"Decision baseline: record_id={baseline.get('record_id')} "
            f"tuple=(gold,silver,delta)={bt}",
            flush=True,
        )
        print(f"Decision: {reason}", flush=True)

    if not accepted:
        return {"accepted": False, "reason": reason, "history_count": len(records), "evicted": None}

    now = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    record_id = f"{EVAL_TYPE}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

    accepted_record = {
        "record_id": record_id,
        "created_at": now,
        "eval_type": EVAL_TYPE,
        "summary": report["summary"],
        "rank_score": round(_safe_float(report["summary"].get("rag_recall_at_3_gold")), 3),
        "outcomes_checksum": report["summary"].get("outcomes_checksum"),
        "command_config": {"output_path": output_path},
        "report_path": "",
    }

    updated, eviction = apply_retention(records, accepted_record)
    report_path = persist_accepted_report(DEFAULT_RECORDS_DIR, record_id, report)
    accepted_record["report_path"] = report_path
    for idx, r in enumerate(updated):
        if r.get("record_id") == record_id:
            updated[idx] = accepted_record
            break

    save_history(history_path, updated)
    if eviction:
        print(f"Retention: evicted {eviction.get('record_id')}", flush=True)
    print(f"Retention: saved {record_id} at {report_path}", flush=True)
    print(f"Retention: history size is {len(updated)} / {MAX_HISTORY_RECORDS}", flush=True)
    return {
        "accepted": True,
        "reason": reason,
        "history_count": len(updated),
        "evicted": eviction.get("record_id") if eviction else None,
    }


def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate the RAG retrieval pipeline against a golden dataset.")
    parser.add_argument("--golden", default=DEFAULT_GOLDEN_PATH, help="Path to golden cases JSON.")
    parser.add_argument("--output", default=DEFAULT_REPORT_PATH, help="Where to write the eval report JSON.")
    parser.add_argument("--history", default=DEFAULT_HISTORY_PATH, help="Path to RAG eval history index.")
    parser.add_argument("--db-path", default=cfg.CHROMA_PATH, help="Chroma DB path.")
    parser.add_argument("--no-retention", action="store_true", help="Skip writing to history.")
    parser.add_argument(
        "--golden-intent",
        action="store_true",
        help="Use golden expected_intent for retrieval (isolates retriever from intent_router). "
        "Default: production path via intent_router.detect_intent(question).",
    )
    parser.add_argument(
        "--intent-model",
        default=None,
        help="Ollama model for intent LLM fallback (default: env ASTRO_MODEL_NAME or astro_engine default).",
    )
    parser.add_argument(
        "--intent-timeout-s",
        type=int,
        default=45,
        help="Timeout for intent_router LLM fallback calls (default: 45).",
    )
    parser.add_argument(
        "--intent-num-ctx",
        type=int,
        default=None,
        help="Ollama num_ctx for intent LLM fallback (default: ASTRO_NUM_CTX env or engine default).",
    )
    parser.add_argument(
        "--judge-model",
        type=str,
        default=None,
        help="Optional Ollama model for JSON faithfulness judge on RAG answers (e.g. llama3.2:3b). "
        "Runs serially (answer + judge per eligible case) to reduce VRAM pressure.",
    )
    parser.add_argument(
        "--max-judge-cases",
        type=int,
        default=None,
        help="Only run answer+judge on the first N golden cases (smoke / cost control). Default: all cases.",
    )
    parser.add_argument(
        "--answer-model",
        type=str,
        default=None,
        help="Ollama model for RAG answer generation when --judge-model is set (default: ASTRO_MODEL_NAME / engine).",
    )
    parser.add_argument(
        "--answer-timeout-s",
        type=int,
        default=None,
        help="Read timeout seconds for answer model (default: ASTRO_OLLAMA_TIMEOUT_S / engine).",
    )
    parser.add_argument(
        "--answer-num-ctx",
        type=int,
        default=None,
        help="Context window for answer generate call (default: ASTRO_NUM_CTX / engine).",
    )
    parser.add_argument(
        "--judge-timeout-s",
        type=int,
        default=90,
        help="Read timeout seconds for judge model (default: 90).",
    )
    parser.add_argument(
        "--judge-num-ctx",
        type=int,
        default=8192,
        help="Context window for judge generate call (default: 8192).",
    )
    parser.add_argument(
        "--no-answer-grounding",
        action="store_true",
        help="When using --judge-model, skip embedding similarity vs retrieved chunks (faster).",
    )
    parser.add_argument(
        "--cross-encoder",
        action="store_true",
        help="Enable cross-encoder rerank (sets rag_config.CROSS_ENCODER_RERANK_ENABLED for this run).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.cross_encoder:
        cfg.CROSS_ENCODER_RERANK_ENABLED = True
    _, _, intent_num_ctx = resolve_ollama_config(
        model_name=args.intent_model,
        timeout_s=None,
        num_ctx=args.intent_num_ctx,
    )
    answer_model, answer_timeout_s, answer_num_ctx = resolve_ollama_config(
        model_name=args.answer_model,
        timeout_s=args.answer_timeout_s,
        num_ctx=args.answer_num_ctx,
    )
    print(
        f"Evaluating RAG: golden={args.golden} db={args.db_path} embed={cfg.EMBED_MODEL} "
        f"golden_intent={args.golden_intent} intent_num_ctx={intent_num_ctx} "
        f"cross_encoder_rerank={cfg.CROSS_ENCODER_RERANK_ENABLED}",
        flush=True,
    )
    if args.judge_model:
        n_golden = len(load_golden(args.golden))
        eligible = n_golden if args.max_judge_cases is None else min(n_golden, max(0, args.max_judge_cases))
        print(
            f"LLM judge: model={args.judge_model} answer_model={answer_model} "
            f"(serial ~{2 * eligible} Ollama calls for {eligible} case(s); "
            f"max_judge_cases={args.max_judge_cases})",
            flush=True,
        )
    report = evaluate(
        args.golden,
        args.db_path,
        golden_intent=args.golden_intent,
        intent_model=args.intent_model,
        intent_timeout_s=args.intent_timeout_s,
        intent_num_ctx=intent_num_ctx,
        judge_model=args.judge_model,
        max_judge_cases=args.max_judge_cases,
        answer_model=answer_model,
        answer_timeout_s=answer_timeout_s,
        answer_num_ctx=answer_num_ctx,
        judge_timeout_s=max(15, args.judge_timeout_s),
        judge_num_ctx=max(1024, args.judge_num_ctx),
        rag_grounding=not args.no_answer_grounding,
    )
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    if not args.no_retention:
        decision = maybe_save_result(report, args.output, args.history)
        report["save_decision"] = decision
        Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
