#!/usr/bin/env python3
"""Summarize ASTRO interaction + feedback JSONL logs."""

import argparse
import json
from collections import Counter
from pathlib import Path


def load_records(path: Path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def main():
    parser = argparse.ArgumentParser(description="Summarize interactions.jsonl")
    parser.add_argument("--path", default="interactions.jsonl")
    args = parser.parse_args()

    rows = load_records(Path(args.path))
    if not rows:
        print(f"No records in {args.path}")
        return

    interactions = [r for r in rows if r.get("event") == "interaction"]
    feedback = [r for r in rows if r.get("event") == "feedback"]

    print(f"total_lines={len(rows)} interactions={len(interactions)} feedback={len(feedback)}")

    if interactions:
        parse_fail = sum(1 for r in interactions if not r.get("parsed_ok"))
        low_conf = sum(
            1
            for r in interactions
            if r.get("confidence_int") is not None and r["confidence_int"] < 50
        )
        print(f"parse_failures={parse_fail} low_confidence_answers={low_conf}")

        intents = Counter(r.get("intent") or "?" for r in interactions)
        print("by_intent:", dict(intents))

        questions = Counter((r.get("question") or "")[:80] for r in interactions)
        print("top_questions:", questions.most_common(5))

    if feedback:
        helpful = sum(1 for r in feedback if r.get("helpful"))
        not_helpful = len(feedback) - helpful
        print(f"feedback_helpful={helpful} feedback_not_helpful={not_helpful}")


if __name__ == "__main__":
    main()
