#!/usr/bin/env python3
"""Fast CI: assert domain prompt builders include required template markers."""

import argparse
import sys

from astro_agent.rag import config as cfg
from astro_agent.chart.engine import build_chart_features
from evals.eval_template_markers import score_template_adherence
from astro_agent.llm.prompts.builder import build_prompt_for_intent

FIXTURE_BIRTH = (1990, 5, 15, 10, 30, "bengaluru")
FIXTURE_QUESTION = "What is the outlook for this native?"
INTENTS = ("career", "health", "wealth", "family", "general")
THRESHOLD = 0.90


def run_checks(structured=None):
    if structured is None:
        structured = cfg.STRUCTURED_OUTPUT_ENABLED
    prev = cfg.STRUCTURED_OUTPUT_ENABLED
    cfg.STRUCTURED_OUTPUT_ENABLED = structured
    try:
        features = build_chart_features(*FIXTURE_BIRTH)
        results = {}
        for intent in INTENTS:
            prompt = build_prompt_for_intent(features, FIXTURE_QUESTION, intent)
            score = score_template_adherence(prompt, intent)
            results[intent] = {"score": score, "prompt_len": len(prompt)}
            if structured:
                ok_extra = "json" in prompt.lower() and "summary" in prompt.lower()
                ok_score = True
            else:
                ok_extra = "Return output in this exact format" in prompt
                ok_score = score >= THRESHOLD
            ok_dasha = "CurrentDashas:" in prompt and "Active Antardasha:" in prompt
            results[intent]["failed"] = not (ok_score and ok_extra and ok_dasha)
        return results
    finally:
        cfg.STRUCTURED_OUTPUT_ENABLED = prev


def main():
    parser = argparse.ArgumentParser(description="Template regression on prompt builders")
    parser.add_argument("--fail-on-regression", action="store_true")
    parser.add_argument("--structured", action="store_true", help="Also test structured-output prompts")
    args = parser.parse_args()

    modes = [False]
    if args.structured:
        modes.append(True)

    failed = False
    for structured in modes:
        label = "structured" if structured else "text"
        print(f"=== mode: {label} ===")
        for intent, row in run_checks(structured=structured).items():
            status = "FAIL" if row.get("failed") else "ok"
            print(f"  {intent}: score={row['score']:.2f} [{status}]")
            if row.get("failed"):
                failed = True

    if failed and args.fail_on_regression:
        sys.exit(1)
    if failed:
        print("Some domains below threshold or missing required sections.")
    else:
        print("All domains passed.")


if __name__ == "__main__":
    main()
