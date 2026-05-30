import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from statistics import mean

from evals.paths import INTENT_ROUTING_REPORT

from astro_agent.chart.engine import build_chart_features
from astro_agent.llm.prompts.builder import build_prompt_for_intent
from astro_agent.llm.client import query_ollama_once, resolve_ollama_config
from astro_agent.routing.intent_router import detect_intent


DEFAULT_ROUTING_CASES = [
    {
        "id": "route_career_1",
        "birth": {"year": 1998, "month": 9, "day": 27, "hour": 13, "minute": 0, "city_name": "delhi"},
        "question": "What is my career growth outlook over the next 2 years?",
        "expected_intent": "career",
        "expected_keywords": ["career", "risk", "opportunity", "confidence"],
    },
    {
        "id": "route_health_1",
        "birth": {"year": 1994, "month": 2, "day": 17, "hour": 12, "minute": 30, "city_name": "bengaluru"},
        "question": "Do you see health concerns or recovery periods soon?",
        "expected_intent": "health",
        "expected_keywords": ["health", "risk", "opportunity", "confidence"],
    },
    {
        "id": "route_wealth_1",
        "birth": {"year": 1996, "month": 12, "day": 26, "hour": 19, "minute": 0, "city_name": "delhi"},
        "question": "How strong are my wealth and savings prospects?",
        "expected_intent": "wealth",
        "expected_keywords": ["wealth", "risk", "opportunity", "confidence"],
    },
    {
        "id": "route_family_1",
        "birth": {"year": 1992, "month": 1, "day": 11, "hour": 8, "minute": 45, "city_name": "mumbai"},
        "question": "How does family and married life look?",
        "expected_intent": "family",
        "expected_keywords": ["family", "risk", "opportunity", "confidence"],
    },
    {
        "id": "route_general_1",
        "birth": {"year": 1991, "month": 7, "day": 5, "hour": 6, "minute": 20, "city_name": "chennai"},
        "question": "Give me an overall outlook of life and major trends.",
        "expected_intent": "general",
        "expected_keywords": ["overall", "risk", "opportunity", "confidence"],
    },
    {
        "id": "route_multi_singlebest",
        "birth": {"year": 1998, "month": 9, "day": 27, "hour": 13, "minute": 0, "city_name": "delhi"},
        "question": "I need both career and health guidance; what matters most?",
        "expected_intent": "career",
        "expected_keywords": ["career", "risk", "opportunity", "confidence"],
    },
]

from eval_scoring import score_keyword_coverage
from eval_template_markers import TEMPLATE_MARKERS, score_template_adherence


def run_one(case, model_name, timeout_s, num_ctx):
    birth = case["birth"]
    intent_info = detect_intent(
        question=case["question"],
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
    prompt = build_prompt_for_intent(features, case["question"], detected_intent)
    response = query_ollama_once(
        prompt,
        temperature=0.2,
        timeout_s=timeout_s,
        model_name=model_name,
        num_ctx=num_ctx,
    )
    intent_match = detected_intent == case["expected_intent"]
    keyword_score = score_keyword_coverage(response, case["expected_keywords"])
    template_score = score_template_adherence(response, case["expected_intent"])
    return {
        "case_id": case["id"],
        "question": case["question"],
        "expected_intent": case["expected_intent"],
        "detected_intent": detected_intent,
        "intent_match": intent_match,
        "intent_method": intent_info.get("method", "unknown"),
        "intent_confidence": intent_info.get("confidence", 0.0),
        "keyword_score": round(keyword_score, 3),
        "template_score": round(template_score, 3),
        "response": response,
    }


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

    intent_accuracy = mean(1.0 if r["intent_match"] else 0.0 for r in rows) if rows else 0.0
    keyword_avg = mean(r["keyword_score"] for r in rows) if rows else 0.0
    template_avg = mean(r["template_score"] for r in rows) if rows else 0.0
    fallback_rate = mean(1.0 if r["intent_method"] != "rules" else 0.0 for r in rows) if rows else 0.0
    summary = {
        "cases": len(rows),
        "model_name": model_name,
        "timeout_s": timeout_s,
        "num_ctx": num_ctx,
        "workers": max(1, workers),
        "intent_accuracy": round(intent_accuracy, 3),
        "keyword_avg": round(keyword_avg, 3),
        "template_avg": round(template_avg, 3),
        "fallback_rate": round(fallback_rate, 3),
    }
    return {"summary": summary, "details": rows}


def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate end-to-end intent-aware prompt routing quality.")
    parser.add_argument(
        "--output",
        type=str,
        default=INTENT_ROUTING_REPORT,
        help="Output JSON report file path.",
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
        help="Parallel case evaluations to run at once (default: 2).",
    )
    parser.add_argument(
        "--num-ctx",
        type=int,
        default=None,
        help="Ollama num_ctx. Defaults to ASTRO_NUM_CTX env or engine default.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    model_name, timeout_s, num_ctx = resolve_ollama_config(
        model_name=args.model,
        timeout_s=args.timeout,
        num_ctx=args.num_ctx,
    )
    print(
        f"Using model={model_name} timeout_s={timeout_s} num_ctx={num_ctx} workers={max(1, args.workers)} "
        f"(ASTRO_MODEL_NAME={os.getenv('ASTRO_MODEL_NAME', '') or 'unset'}, "
        f"ASTRO_OLLAMA_TIMEOUT_S={os.getenv('ASTRO_OLLAMA_TIMEOUT_S', '') or 'unset'}, "
        f"ASTRO_NUM_CTX={os.getenv('ASTRO_NUM_CTX', '') or 'unset'})",
        flush=True,
    )
    report = evaluate(
        DEFAULT_ROUTING_CASES,
        model_name=model_name,
        timeout_s=timeout_s,
        num_ctx=num_ctx,
        workers=max(1, args.workers),
    )
    with open(args.output, "w", encoding="utf-8") as fp:
        json.dump(report, fp, indent=2)
    print(json.dumps(report["summary"], indent=2))
