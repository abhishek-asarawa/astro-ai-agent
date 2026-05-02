import argparse
import json
import math
import os
import re
from datetime import datetime
from pathlib import Path
from statistics import mean
from concurrent.futures import ThreadPoolExecutor, as_completed

from astro_engine import (
    build_chart_features,
    build_career_prompt,
    build_rag_enriched_prompt,
    generate_full_chart,
    query_ollama_once,
    resolve_ollama_config,
)
import rag_search


DEFAULT_CASES = [
    {
        "id": "case_delhi_1998",
        "birth": {"year": 1998, "month": 9, "day": 27, "hour": 13, "minute": 0, "city_name": "delhi"},
        "question": "What is the professional outlook for this chart?",
        "expected_keywords": ["10th", "dasha", "career", "confidence"],
    },
    {
        "id": "case_bengaluru_1994",
        "birth": {"year": 1994, "month": 2, "day": 17, "hour": 12, "minute": 30, "city_name": "bengaluru"},
        "question": "How stable is career growth in the next few years?",
        "expected_keywords": ["growth", "risk", "opportunity", "dasha"],
    },
]

DEFAULT_EVAL_TYPE = "career"
DEFAULT_HISTORY_PATH = "eval_history.json"
DEFAULT_RECORDS_DIR = "eval_records"
MAX_HISTORY_RECORDS = 3

_REASONING_BLOCK_RE = re.compile(
    r"(?:<think>.*?</think>|<redacted_reasoning>.*?</redacted_reasoning>)",
    re.IGNORECASE | re.DOTALL,
)


def _text_for_scoring(raw_response: str) -> str:
    """Drop common reasoning wrappers so embedding/judge see the final answer."""
    if not raw_response:
        return ""
    text = _REASONING_BLOCK_RE.sub("", raw_response)
    return text.strip()


def _cosine_similarity(vec_a, vec_b) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(x * y for x, y in zip(vec_a, vec_b))
    na = math.sqrt(sum(x * x for x in vec_a))
    nb = math.sqrt(sum(y * y for y in vec_b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _chunk_text(chunk) -> str:
    if chunk is None:
        return ""
    if isinstance(chunk, dict):
        return (chunk.get("text") or "").strip()
    return (getattr(chunk, "text", None) or "").strip()


def score_grounding_embedding(response: str, retrieved_chunks, max_chars: int = 7500) -> dict:
    """Max/mean cosine similarity between answer embedding and each retrieved chunk (same space as RAG)."""
    text = _text_for_scoring(response)
    if not text or not retrieved_chunks:
        return {"grounding_max_sim": 0.0, "grounding_mean_sim": 0.0, "grounding_error": None}

    try:
        truncated_answer = text[:max_chars]
        answer_emb = rag_search.embed_query(truncated_answer)
        if not answer_emb:
            return {
                "grounding_max_sim": 0.0,
                "grounding_mean_sim": 0.0,
                "grounding_error": "empty_answer_embedding",
            }
        sims = []
        for chunk in retrieved_chunks:
            ct = _chunk_text(chunk)[:max_chars]
            if not ct:
                continue
            emb = rag_search.embed_query(ct)
            if not emb:
                continue
            sims.append(_cosine_similarity(answer_emb, emb))
        if not sims:
            return {
                "grounding_max_sim": 0.0,
                "grounding_mean_sim": 0.0,
                "grounding_error": "no_chunk_embeddings",
            }
        return {
            "grounding_max_sim": round(max(sims), 4),
            "grounding_mean_sim": round(sum(sims) / len(sims), 4),
            "grounding_error": None,
        }
    except Exception as exc:
        return {
            "grounding_max_sim": 0.0,
            "grounding_mean_sim": 0.0,
            "grounding_error": str(exc),
        }


def _parse_judge_json(text: str) -> dict:
    if not text:
        return {}
    cleaned = text.strip()
    if "```" in cleaned:
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return {}


def run_grounding_judge(
    model_answer: str,
    retrieved_chunks,
    judge_model: str,
    timeout_s: int = 90,
    num_ctx: int = 8192,
    max_sources_chars: int = 12000,
    max_answer_chars: int = 6000,
) -> dict:
    """Small LLM scores how well the answer is supported by retrieved sources."""
    answer = _text_for_scoring(model_answer)[:max_answer_chars]
    parts = []
    for ch in retrieved_chunks or []:
        ref = getattr(ch, "ref_id", None) if not isinstance(ch, dict) else ch.get("ref_id")
        body = _chunk_text(ch)
        if not body:
            continue
        parts.append(f"[{ref}]: {body}")
    sources = "\n\n".join(parts)[:max_sources_chars]
    if not answer.strip() or not sources.strip():
        return {
            "judge_grounding": None,
            "judge_supported_ratio": None,
            "judge_note": "",
            "judge_raw": "",
            "judge_error": "missing_answer_or_sources",
        }

    prompt = (
        "You evaluate whether an astrologer's answer stays grounded in the given classical SOURCES.\n\n"
        "SOURCES (excerpts only):\n"
        f"{sources}\n\n"
        "MODEL ANSWER:\n"
        f"{answer}\n\n"
        "Score ONLY classical / rule claims in the answer against SOURCES. Ignore chart-specific facts.\n"
        "Reply with ONLY valid JSON on one line, no markdown:\n"
        '{"grounding": <integer 1-5>, "supported_ratio": <number 0-1>, "note": "<short string>"}\n'
        "1 = unsupported or contradicts sources; 3 = partly supported; 5 = well supported where it cites classical rules.\n"
    )
    raw = query_ollama_once(
        prompt,
        temperature=0.0,
        timeout_s=timeout_s,
        model_name=judge_model,
        num_ctx=num_ctx,
    )
    parsed = _parse_judge_json(raw)
    grounding = parsed.get("grounding")
    ratio = parsed.get("supported_ratio")
    note = parsed.get("note", "")
    try:
        grounding = int(grounding) if grounding is not None else None
    except (TypeError, ValueError):
        grounding = None
    try:
        ratio = float(ratio) if ratio is not None else None
    except (TypeError, ValueError):
        ratio = None
    err = None
    if grounding is None:
        err = "judge_parse_failed"
    return {
        "judge_grounding": grounding,
        "judge_supported_ratio": ratio,
        "judge_note": note if isinstance(note, str) else str(note),
        "judge_raw": (raw or "")[:2000],
        "judge_error": err,
    }


def get_cases_for_eval_type(eval_type):
    """Evaluation registry entrypoint for extensibility."""
    if eval_type == "career":
        return DEFAULT_CASES
    raise ValueError(f"Unsupported eval_type: {eval_type}")


def build_enriched_prompt(eval_type, case):
    """Build enriched prompt for selected evaluation type."""
    if eval_type == "career":
        birth = case["birth"]
        features = build_chart_features(
            birth["year"], birth["month"], birth["day"], birth["hour"], birth["minute"], birth["city_name"]
        )
        return build_career_prompt(features, case["question"])
    raise ValueError(f"Unsupported eval_type: {eval_type}")


def build_baseline_prompt(case):
    birth = case["birth"]
    facts = generate_full_chart(
        birth["year"], birth["month"], birth["day"], birth["hour"], birth["minute"], birth["city_name"]
    )
    return (
        "You are an expert Vedic Astrologer. Provide a career prediction for the native.\n\n"
        f"DATA:\n{facts}\n\nQUESTION: {case['question']}"
    )


def score_keyword_coverage(response, expected_keywords):
    if not response.strip():
        return 0.0
    text = response.lower()
    hits = sum(1 for kw in expected_keywords if kw.lower() in text)
    return hits / max(1, len(expected_keywords))


def score_template_adherence(response):
    required_markers = [
        "careersummary:",
        "evidence:",
        "careerrisk:",
        "careeropportunity:",
        "confidence:",
    ]
    text = response.lower()
    hits = sum(1 for marker in required_markers if marker in text)
    return hits / len(required_markers)


def run_once(
    eval_type,
    case,
    enriched,
    rag_enriched,
    timeout_s,
    model_name,
    num_ctx,
    *,
    rag_grounding=True,
    judge_model=None,
    judge_timeout_s=90,
    judge_num_ctx=8192,
):
    if rag_enriched:
        birth = case["birth"]
        features = build_chart_features(
            birth["year"], birth["month"], birth["day"], birth["hour"], birth["minute"], birth["city_name"]
        )
        bundle = build_rag_enriched_prompt(features, case["question"], "career")
        response = query_ollama_once(
            bundle["prompt"],
            temperature=0.2,
            timeout_s=timeout_s,
            model_name=model_name,
            allowed_refs=bundle["allowed_refs"],
            num_ctx=num_ctx,
        )
        keyword_score = score_keyword_coverage(response, case["expected_keywords"])
        template_score = score_template_adherence(response)
        citation_count = len(re.findall(r"\[ref:[^\]]+\]", response))
        retrieved = bundle.get("retrieved") or []
        out = {
            "response": response,
            "keyword_score": round(keyword_score, 3),
            "template_score": round(template_score, 3),
            "citation_count": citation_count,
            "rag_active": bundle.get("rag_active", False),
        }
        if rag_grounding and retrieved and bundle.get("allowed_refs"):
            g = score_grounding_embedding(response, retrieved)
            out["grounding_max_sim"] = g["grounding_max_sim"]
            out["grounding_mean_sim"] = g["grounding_mean_sim"]
            if g.get("grounding_error"):
                out["grounding_error"] = g["grounding_error"]
        else:
            out["grounding_max_sim"] = None
            out["grounding_mean_sim"] = None

        if judge_model and retrieved and bundle.get("allowed_refs"):
            j = run_grounding_judge(
                response,
                retrieved,
                judge_model=judge_model,
                timeout_s=judge_timeout_s,
                num_ctx=judge_num_ctx,
            )
            out.update(
                {
                    "judge_grounding": j.get("judge_grounding"),
                    "judge_supported_ratio": j.get("judge_supported_ratio"),
                    "judge_note": j.get("judge_note"),
                    "judge_error": j.get("judge_error"),
                }
            )
            if j.get("judge_raw"):
                out["judge_raw"] = j["judge_raw"]
        return out
    if enriched:
        prompt = build_enriched_prompt(eval_type, case)
    else:
        prompt = build_baseline_prompt(case)
    response = query_ollama_once(
        prompt,
        temperature=0.2,
        timeout_s=timeout_s,
        model_name=model_name,
        num_ctx=num_ctx,
    )
    keyword_score = score_keyword_coverage(response, case["expected_keywords"])
    template_score = score_template_adherence(response) if enriched else 0.0
    return {
        "response": response,
        "keyword_score": round(keyword_score, 3),
        "template_score": round(template_score, 3),
    }


def _build_jobs(cases, runs_per_case, rag_enabled=False):
    jobs = []
    for case in cases:
        for run_idx in range(1, runs_per_case + 1):
            jobs.append(
                {
                    "case": case,
                    "run_idx": run_idx,
                    "mode": "baseline",
                    "enriched": False,
                }
            )
            jobs.append(
                {
                    "case": case,
                    "run_idx": run_idx,
                    "mode": "enriched",
                    "enriched": True,
                    "rag_enriched": False,
                }
            )
            if rag_enabled:
                jobs.append(
                    {
                        "case": case,
                        "run_idx": run_idx,
                        "mode": "rag_enriched",
                        "enriched": False,
                        "rag_enriched": True,
                    }
                )
    return jobs


def evaluate(
    eval_type,
    cases,
    runs_per_case,
    timeout_s,
    model_name,
    num_ctx,
    workers,
    rag_enabled=False,
    *,
    rag_grounding=True,
    judge_model=None,
    judge_timeout_s=90,
    judge_num_ctx=8192,
):
    report = {"baseline": [], "enriched": [], "rag_enriched": [] if rag_enabled else None}
    jobs = _build_jobs(cases, runs_per_case, rag_enabled=rag_enabled)
    total_calls = len(jobs)
    completed = 0

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        future_to_job = {
            executor.submit(
                run_once,
                eval_type,
                job["case"],
                job["enriched"],
                job.get("rag_enriched", False),
                timeout_s,
                model_name,
                num_ctx,
                rag_grounding=rag_grounding,
                judge_model=judge_model,
                judge_timeout_s=judge_timeout_s,
                judge_num_ctx=judge_num_ctx,
            ): job
            for job in jobs
        }

        for future in as_completed(future_to_job):
            job = future_to_job[future]
            completed += 1
            print(
                f"[{completed}/{total_calls}] {job['mode']} | case={job['case']['id']} | run={job['run_idx']}",
                flush=True,
            )
            try:
                result = future.result()
            except Exception as exc:
                result = {
                    "response": "",
                    "keyword_score": 0.0,
                    "template_score": 0.0,
                    "error": str(exc),
                    "grounding_max_sim": None,
                    "grounding_mean_sim": None,
                    "judge_grounding": None,
                }

            entry = {"case_id": job["case"]["id"], **result}
            report[job["mode"]].append(entry)

    baseline_keyword = mean(item["keyword_score"] for item in report["baseline"])
    enriched_keyword = mean(item["keyword_score"] for item in report["enriched"])
    enriched_template = mean(item["template_score"] for item in report["enriched"])

    summary = {
        "eval_type": eval_type,
        "runs_per_case": runs_per_case,
        "cases": len(cases),
        "model_name": model_name,
        "timeout_s": timeout_s,
        "num_ctx": num_ctx,
        "baseline_keyword_avg": round(baseline_keyword, 3),
        "enriched_keyword_avg": round(enriched_keyword, 3),
        "enriched_template_avg": round(enriched_template, 3),
        "delta_keyword_avg": round(enriched_keyword - baseline_keyword, 3),
    }
    if rag_enabled:
        rag_entries = report.get("rag_enriched") or []
        rag_keyword = mean(item["keyword_score"] for item in rag_entries) if rag_entries else 0.0
        rag_template = mean(item["template_score"] for item in rag_entries) if rag_entries else 0.0
        rag_citations = mean(item.get("citation_count", 0) for item in rag_entries) if rag_entries else 0.0
        summary.update(
            {
                "rag_enriched_keyword_avg": round(rag_keyword, 3),
                "rag_enriched_template_avg": round(rag_template, 3),
                "rag_enriched_citation_avg": round(rag_citations, 3),
                "rag_delta_vs_enriched_keyword_avg": round(rag_keyword - enriched_keyword, 3),
            }
        )
        gmax_vals = [
            item["grounding_max_sim"]
            for item in rag_entries
            if item.get("grounding_max_sim") is not None
        ]
        gmean_vals = [
            item["grounding_mean_sim"]
            for item in rag_entries
            if item.get("grounding_mean_sim") is not None
        ]
        if gmax_vals:
            summary["rag_grounding_max_sim_avg"] = round(mean(gmax_vals), 4)
            summary["rag_grounding_mean_sim_avg"] = round(mean(gmean_vals), 4)
        judge_vals = [
            item["judge_grounding"]
            for item in rag_entries
            if item.get("judge_grounding") is not None
        ]
        if judge_vals:
            summary["rag_judge_grounding_avg"] = round(mean(judge_vals), 3)
        ratio_vals = [
            item["judge_supported_ratio"]
            for item in rag_entries
            if item.get("judge_supported_ratio") is not None
        ]
        if ratio_vals:
            summary["rag_judge_supported_ratio_avg"] = round(mean(ratio_vals), 3)
        embed_model = None
        try:
            import rag_config as _rcfg

            embed_model = getattr(_rcfg, "EMBED_MODEL", None)
        except Exception:
            pass
        if embed_model:
            summary["rag_grounding_embed_model"] = embed_model
        if judge_model:
            summary["rag_judge_model"] = judge_model
    else:
        report.pop("rag_enriched", None)

    return {"summary": summary, "details": report}


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _rank_tuple_legacy(record):
    summary = record.get("summary", {})
    return (
        _safe_float(summary.get("enriched_keyword_avg")),
        _safe_float(summary.get("enriched_template_avg")),
    )


def _has_rag_retention_metrics(summary: dict) -> bool:
    if not summary:
        return False
    return (
        summary.get("rag_judge_grounding_avg") is not None
        or summary.get("rag_grounding_max_sim_avg") is not None
    )


def _rank_tuple_rag_summary(summary: dict):
    """Lexicographic rank: judge score, embedding grounding, citations, RAG template."""
    return (
        _safe_float(summary.get("rag_judge_grounding_avg"), -1.0),
        _safe_float(summary.get("rag_grounding_max_sim_avg")),
        _safe_float(summary.get("rag_enriched_citation_avg")),
        _safe_float(summary.get("rag_enriched_template_avg")),
    )


def select_global_baseline(records, retention_mode="legacy"):
    if not records:
        return None
    if retention_mode == "rag":
        eligible = [r for r in records if _has_rag_retention_metrics(r.get("summary", {}))]
        if not eligible:
            return None
        return max(eligible, key=lambda r: _rank_tuple_rag_summary(r.get("summary", {})))
    return max(records, key=_rank_tuple_legacy)


def load_history(history_path):
    path = Path(history_path)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Warning: could not read history at {history_path}: {exc}. Starting with empty history.", flush=True)
        return []
    if isinstance(data, dict):
        records = data.get("records", [])
    elif isinstance(data, list):
        records = data
    else:
        records = []
    return records if isinstance(records, list) else []


def save_history(history_path, records):
    path = Path(history_path)
    payload = {"version": 1, "records": records}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def passes_guardrails(new_summary, baseline_record, retention_mode="legacy"):
    if baseline_record is None:
        return True, "no past record found"

    if retention_mode == "rag":
        baseline_summary = baseline_record.get("summary", {})
        if not _has_rag_retention_metrics(baseline_summary):
            return True, "no prior accepted run with RAG grounding/judge metrics"
        new_r = _rank_tuple_rag_summary(new_summary)
        base_r = _rank_tuple_rag_summary(baseline_summary)
        if new_r <= base_r:
            return (
                False,
                (
                    "rejected: RAG composite did not improve "
                    f"(new={new_r} <= base={base_r})"
                ),
            )
        return True, "accepted: RAG guardrails passed"

    baseline_summary = baseline_record.get("summary", {})
    new_keyword = _safe_float(new_summary.get("enriched_keyword_avg"))
    base_keyword = _safe_float(baseline_summary.get("enriched_keyword_avg"))
    new_template = _safe_float(new_summary.get("enriched_template_avg"))
    base_template = _safe_float(baseline_summary.get("enriched_template_avg"))

    if new_keyword <= base_keyword:
        return (
            False,
            (
                "rejected: enriched_keyword_avg did not improve "
                f"({new_keyword:.3f} <= {base_keyword:.3f})"
            ),
        )
    if new_template < base_template:
        return (
            False,
            (
                "rejected: enriched_template_avg dropped "
                f"({new_template:.3f} < {base_template:.3f})"
            ),
        )
    return True, "accepted: guardrails passed"


def _least_good_bucket(records, retention_mode="legacy"):
    key = _rank_tuple_legacy if retention_mode == "legacy" else lambda r: _rank_tuple_rag_summary(r.get("summary", {}))
    min_rank = min(key(r) for r in records)
    return [r for r in records if key(r) == min_rank]


def apply_retention_max3(records, new_record, retention_mode="legacy"):
    eviction = None
    if len(records) < MAX_HISTORY_RECORDS:
        records.append(new_record)
        return records, eviction

    least_good = _least_good_bucket(records, retention_mode=retention_mode)
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


def maybe_save_result(
    report,
    model_name,
    timeout_s,
    workers,
    runs_per_case,
    output_path,
    eval_type,
    history_path,
    retention_mode="legacy",
):
    records = load_history(history_path)
    baseline = select_global_baseline(records, retention_mode=retention_mode)
    accepted, reason = passes_guardrails(report["summary"], baseline, retention_mode=retention_mode)

    if baseline is None:
        print("Decision: accept run because no past record exists.", flush=True)
    else:
        base_id = baseline.get("record_id", "unknown")
        base_sum = baseline.get("summary", {})
        if retention_mode == "rag":
            print(
                "Decision baseline: "
                f"record_id={base_id} "
                f"rag_judge_grounding_avg={base_sum.get('rag_judge_grounding_avg')} "
                f"rag_grounding_max_sim_avg={base_sum.get('rag_grounding_max_sim_avg')} "
                f"rag_enriched_citation_avg={_safe_float(base_sum.get('rag_enriched_citation_avg')):.3f}",
                flush=True,
            )
        else:
            print(
                "Decision baseline: "
                f"record_id={base_id} "
                f"enriched_keyword_avg={_safe_float(base_sum.get('enriched_keyword_avg')):.3f} "
                f"enriched_template_avg={_safe_float(base_sum.get('enriched_template_avg')):.3f}",
                flush=True,
            )
        print(f"Decision: {reason}", flush=True)

    if not accepted:
        return {"accepted": False, "reason": reason, "history_count": len(records), "evicted": None}

    now = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    record_id = f"{eval_type}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    summ = report["summary"]
    if retention_mode == "rag":
        if summ.get("rag_judge_grounding_avg") is not None:
            rank_score = round(_safe_float(summ.get("rag_judge_grounding_avg")), 3)
        else:
            rank_score = round(_safe_float(summ.get("rag_grounding_max_sim_avg")), 3)
    else:
        rank_score = round(_safe_float(summ.get("enriched_keyword_avg")), 3)

    accepted_record = {
        "record_id": record_id,
        "created_at": now,
        "eval_type": eval_type,
        "summary": report["summary"],
        "rank_score": rank_score,
        "command_config": {
            "model_name": model_name,
            "timeout_s": timeout_s,
            "num_ctx": report.get("summary", {}).get("num_ctx"),
            "workers": workers,
            "runs_per_case": runs_per_case,
            "output_path": output_path,
            "retention_mode": retention_mode,
        },
        "report_path": "",
    }

    updated_records, eviction = apply_retention_max3(records, accepted_record, retention_mode=retention_mode)
    report_path = persist_accepted_report(DEFAULT_RECORDS_DIR, record_id, report)
    accepted_record["report_path"] = report_path
    for idx, record in enumerate(updated_records):
        if record.get("record_id") == record_id:
            updated_records[idx] = accepted_record
            break

    save_history(history_path, updated_records)
    if eviction:
        print(
            "Retention: evicted record "
            f"{eviction.get('record_id')} with rank_score={_safe_float(eviction.get('rank_score')):.3f}",
            flush=True,
        )
    print(f"Retention: saved accepted record {record_id} at {report_path}", flush=True)
    print(f"Retention: history size is now {len(updated_records)} / {MAX_HISTORY_RECORDS}", flush=True)
    return {
        "accepted": True,
        "reason": reason,
        "history_count": len(updated_records),
        "evicted": eviction.get("record_id") if eviction else None,
    }


def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate baseline vs enriched prompts with smart retention.")
    parser.add_argument(
        "--eval-type",
        type=str,
        default=DEFAULT_EVAL_TYPE,
        help="Evaluation type to run (default: career).",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=2,
        help="How many repeated runs per case for each prompt style (default: 2).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="career_eval_report.json",
        help="Output JSON report file path.",
    )
    parser.add_argument(
        "--history",
        type=str,
        default=DEFAULT_HISTORY_PATH,
        help="Path to persistent accepted-results history index JSON.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Per-call Ollama read timeout in seconds. Defaults to ASTRO_OLLAMA_TIMEOUT_S env or engine default.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Ollama model name. Defaults to ASTRO_MODEL_NAME env or engine default.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=2,
        help="Parallel Ollama requests to run at once (default: 2).",
    )
    parser.add_argument(
        "--num-ctx",
        type=int,
        default=None,
        help="Ollama context window for eval calls. Defaults to ASTRO_NUM_CTX env or engine default.",
    )
    parser.add_argument(
        "--rag",
        action="store_true",
        help="Also run rag_enriched prompt mode in addition to baseline and enriched.",
    )
    parser.add_argument(
        "--retention-mode",
        type=str,
        choices=("legacy", "rag"),
        default="legacy",
        help="History guardrails: legacy=enriched keyword/template; rag=judge+embedding+citations composite (use with --rag).",
    )
    parser.add_argument(
        "--no-grounding",
        action="store_true",
        help="Skip embedding similarity vs retrieved chunks for RAG runs.",
    )
    parser.add_argument(
        "--judge-model",
        type=str,
        default=None,
        help="Optional Ollama model for JSON faithfulness judge on RAG answers (e.g. llama3.2:3b).",
    )
    parser.add_argument(
        "--judge-timeout",
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
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    model_name, resolved_timeout, resolved_num_ctx = resolve_ollama_config(
        model_name=args.model,
        timeout_s=args.timeout,
        num_ctx=args.num_ctx,
    )
    print(
        f"Using eval_type={args.eval_type} model={model_name} timeout_s={resolved_timeout} num_ctx={resolved_num_ctx} "
        f"workers={max(1, args.workers)} rag={args.rag} retention_mode={args.retention_mode} "
        f"grounding={not args.no_grounding} judge_model={args.judge_model or 'off'} "
        f"(ASTRO_MODEL_NAME={os.getenv('ASTRO_MODEL_NAME', '') or 'unset'}, "
        f"ASTRO_OLLAMA_TIMEOUT_S={os.getenv('ASTRO_OLLAMA_TIMEOUT_S', '') or 'unset'}, "
        f"ASTRO_NUM_CTX={os.getenv('ASTRO_NUM_CTX', '') or 'unset'})",
        flush=True,
    )
    if args.retention_mode == "rag" and args.rag and args.no_grounding and not args.judge_model:
        print(
            "Warning: --retention-mode rag with --no-grounding and no --judge-model "
            "leaves weak RAG retention scores; add a judge or enable grounding.",
            flush=True,
        )

    cases = get_cases_for_eval_type(args.eval_type)
    result = evaluate(
        args.eval_type,
        cases,
        runs_per_case=max(1, args.runs),
        timeout_s=resolved_timeout,
        model_name=model_name,
        num_ctx=resolved_num_ctx,
        workers=max(1, args.workers),
        rag_enabled=args.rag,
        rag_grounding=not args.no_grounding,
        judge_model=args.judge_model,
        judge_timeout_s=max(15, args.judge_timeout),
        judge_num_ctx=max(1024, args.judge_num_ctx),
    )
    result["summary"]["retention_mode"] = args.retention_mode
    with open(args.output, "w", encoding="utf-8") as fp:
        json.dump(result, fp, indent=2)
    decision = maybe_save_result(
        report=result,
        model_name=model_name,
        timeout_s=resolved_timeout,
        workers=max(1, args.workers),
        runs_per_case=max(1, args.runs),
        output_path=args.output,
        eval_type=args.eval_type,
        history_path=args.history,
        retention_mode=args.retention_mode,
    )
    result["save_decision"] = decision
    with open(args.output, "w", encoding="utf-8") as fp:
        json.dump(result, fp, indent=2)
    print(json.dumps(result["summary"], indent=2))
