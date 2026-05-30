import argparse
import json
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from statistics import mean

from astro_agent.chart.engine import build_chart_features
from astro_agent.llm.prompts.builder import build_prompt_for_intent
from astro_agent.llm.client import query_ollama_once, resolve_ollama_config
from astro_agent.routing.intent_router import detect_intent
from data.golden.schema import GoldenCase, load_golden_cases
from evals.eval_scoring import score_keyword_coverage
from evals.eval_template_markers import score_template_adherence

from evals.paths import RECORDS_DIR

DEFAULT_GOLDEN_PATH = "data/golden/real_world_questions_v0.json"
DEFAULT_RECORDS_DIR = RECORDS_DIR


def run_one(case: GoldenCase, model_name, timeout_s, num_ctx):
    birth = case.birth
    intent_info = detect_intent(
        question=case.question,
        model_name=model_name,
        timeout_s=min(45, timeout_s),
        num_ctx=num_ctx,
    )
    detected_intent = intent_info.get("intent", "general")
    features = build_chart_features(
        birth["year"],
        birth["month"],
        birth["day"],
        birth["hour"],
        birth["minute"],
        birth["city_name"],
    )
    prompt = build_prompt_for_intent(features, case.question, detected_intent)
    response = query_ollama_once(
        prompt,
        temperature=0.2,
        timeout_s=timeout_s,
        model_name=model_name,
        num_ctx=num_ctx,
    )
    intent_match = detected_intent == case.expected_intent
    keyword_score = score_keyword_coverage(response, case.expected_keywords)
    template_score = score_template_adherence(response, detected_intent)
    return {
        "case_id": case.case_id,
        "question": case.question,
        "tags": case.tags,
        "bphs_chapter_hint": case.bphs_chapter_hint,
        "expected_intent": case.expected_intent,
        "detected_intent": detected_intent,
        "intent_match": intent_match,
        "intent_method": intent_info.get("method", "unknown"),
        "intent_confidence": intent_info.get("confidence", 0.0),
        "keyword_score": round(keyword_score, 3),
        "template_score": round(template_score, 3),
        "response": response,
    }


def _accuracy(rows):
    if not rows:
        return 0.0
    return mean(1.0 if r["intent_match"] else 0.0 for r in rows)


def _accuracy_by_key(rows, key_fn):
    buckets = defaultdict(list)
    for row in rows:
        for key in key_fn(row):
            buckets[key].append(row)
    return {key: round(_accuracy(items), 3) for key, items in sorted(buckets.items())}


def evaluate(cases, model_name, timeout_s, num_ctx, workers):
    rows = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = [executor.submit(run_one, case, model_name, timeout_s, num_ctx) for case in cases]
        for idx, future in enumerate(as_completed(futures), start=1):
            print(f"[{idx}/{len(futures)}] completed", flush=True)
            try:
                rows.append(future.result())
            except Exception as exc:
                rows.append(
                    {
                        "case_id": "unknown",
                        "question": "",
                        "tags": [],
                        "expected_intent": "general",
                        "detected_intent": "general",
                        "intent_match": False,
                        "intent_method": "error",
                        "intent_confidence": 0.0,
                        "keyword_score": 0.0,
                        "template_score": 0.0,
                        "response": "",
                        "error": str(exc),
                    }
                )

    india_rows = [r for r in rows if "india_trending" in (r.get("tags") or [])]
    generic_rows = [r for r in rows if "india_trending" not in (r.get("tags") or [])]

    summary = {
        "cases": len(rows),
        "golden_path": "",
        "model_name": model_name,
        "timeout_s": timeout_s,
        "num_ctx": num_ctx,
        "workers": max(1, workers),
        "intent_accuracy": round(_accuracy(rows), 3),
        "intent_accuracy_generic": round(_accuracy(generic_rows), 3) if generic_rows else None,
        "intent_accuracy_india_trending": round(_accuracy(india_rows), 3) if india_rows else None,
        "intent_accuracy_per_domain": _accuracy_by_key(rows, lambda r: [r["expected_intent"]]),
        "intent_accuracy_per_tag": _accuracy_by_key(
            rows,
            lambda r: r.get("tags") or [],
        ),
        "keyword_avg": round(mean(r["keyword_score"] for r in rows), 3) if rows else 0.0,
        "template_avg": round(mean(r["template_score"] for r in rows), 3) if rows else 0.0,
        "fallback_rate": round(
            mean(1.0 if r.get("intent_method") != "rules" else 0.0 for r in rows),
            3,
        )
        if rows
        else 0.0,
    }
    return {"summary": summary, "details": rows}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Evaluate real-world colloquial questions against intent routing and responses."
    )
    parser.add_argument(
        "--golden",
        type=str,
        default=DEFAULT_GOLDEN_PATH,
        help="Path to golden JSON cases (default: data/golden/real_world_questions_v0.json).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Output JSON report path. Defaults to eval_reports/records/real_world_eval_<timestamp>.json",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Per-call Ollama read timeout in seconds.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Ollama model name.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=2,
        help="Parallel case evaluations (default: 2).",
    )
    parser.add_argument(
        "--num-ctx",
        type=int,
        default=None,
        help="Ollama num_ctx.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    model_name, timeout_s, num_ctx = resolve_ollama_config(
        model_name=args.model,
        timeout_s=args.timeout,
        num_ctx=args.num_ctx,
    )
    cases = load_golden_cases(args.golden)
    print(
        f"Using golden={args.golden} cases={len(cases)} model={model_name} "
        f"timeout_s={timeout_s} num_ctx={num_ctx} workers={max(1, args.workers)} "
        f"(ASTRO_MODEL_NAME={os.getenv('ASTRO_MODEL_NAME', '') or 'unset'})",
        flush=True,
    )
    report = evaluate(
        cases,
        model_name=model_name,
        timeout_s=timeout_s,
        num_ctx=num_ctx,
        workers=max(1, args.workers),
    )
    report["summary"]["golden_path"] = args.golden
    if args.output:
        output_path = Path(args.output)
    else:
        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        out_dir = Path(DEFAULT_RECORDS_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / f"real_world_eval_{stamp}.json"
    report["summary"]["output_path"] = str(output_path)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
