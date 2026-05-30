import argparse
import json
import os
from statistics import mean

from evals.paths import INTENT_DETECTION_REPORT

from astro_agent.llm.client import resolve_ollama_config
from astro_agent.routing.intent_router import detect_intent


DEFAULT_INTENT_CASES = [
    {"id": "intent_career", "question": "Will I get career growth and job promotion?", "expected_intent": "career"},
    {"id": "intent_health", "question": "Any health issues or medical risks in near future?", "expected_intent": "health"},
    {"id": "intent_wealth", "question": "How is wealth, savings and financial stability?", "expected_intent": "wealth"},
    {"id": "intent_family", "question": "How is family life and marriage harmony?", "expected_intent": "family"},
    {"id": "intent_general", "question": "What is the overall life outlook for this chart?", "expected_intent": "general"},
    {"id": "intent_multi", "question": "Career and health both look unstable, what should I focus on?", "expected_intent": "career"},
]


def evaluate_cases(cases, model_name, timeout_s, num_ctx):
    rows = []
    for case in cases:
        result = detect_intent(
            question=case["question"],
            model_name=model_name,
            timeout_s=timeout_s,
            num_ctx=num_ctx,
        )
        detected = result.get("intent", "general")
        matched = detected == case["expected_intent"]
        rows.append(
            {
                "id": case["id"],
                "question": case["question"],
                "expected_intent": case["expected_intent"],
                "detected_intent": detected,
                "match": matched,
                "method": result.get("method", "unknown"),
                "confidence": result.get("confidence", 0.0),
                "rule_scores": result.get("rule_scores", {}),
            }
        )

    accuracy = mean(1.0 if r["match"] else 0.0 for r in rows) if rows else 0.0
    fallback_rate = (
        mean(1.0 if r["method"] != "rules" else 0.0 for r in rows) if rows else 0.0
    )
    summary = {
        "cases": len(rows),
        "model_name": model_name,
        "timeout_s": timeout_s,
        "num_ctx": num_ctx,
        "intent_accuracy": round(accuracy, 3),
        "fallback_rate": round(fallback_rate, 3),
    }
    return {"summary": summary, "details": rows}


def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate intent detection quality for routing.")
    parser.add_argument(
        "--output",
        type=str,
        default=INTENT_DETECTION_REPORT,
        help="Output JSON report file path.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Per-call timeout in seconds. Defaults to ASTRO_OLLAMA_TIMEOUT_S env or engine default.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Ollama model name. Defaults to ASTRO_MODEL_NAME env or engine default.",
    )
    parser.add_argument(
        "--num-ctx",
        type=int,
        default=None,
        help="Ollama num_ctx for intent LLM fallback. Defaults to ASTRO_NUM_CTX env or engine default.",
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
        f"Using model={model_name} timeout_s={timeout_s} num_ctx={num_ctx} "
        f"(ASTRO_MODEL_NAME={os.getenv('ASTRO_MODEL_NAME', '') or 'unset'}, "
        f"ASTRO_OLLAMA_TIMEOUT_S={os.getenv('ASTRO_OLLAMA_TIMEOUT_S', '') or 'unset'}, "
        f"ASTRO_NUM_CTX={os.getenv('ASTRO_NUM_CTX', '') or 'unset'})",
        flush=True,
    )
    report = evaluate_cases(
        DEFAULT_INTENT_CASES,
        model_name=model_name,
        timeout_s=min(45, timeout_s),
        num_ctx=num_ctx,
    )
    with open(args.output, "w", encoding="utf-8") as fp:
        json.dump(report, fp, indent=2)
    print(json.dumps(report["summary"], indent=2))
