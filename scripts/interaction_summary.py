#!/usr/bin/env python3
"""Summarize ASTRO interaction + feedback JSONL logs."""

import argparse
import json
from collections import Counter, defaultdict
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


def build_negative_feedback_report(rows: list[dict]) -> list[dict]:
    """Join negative feedback rows to their interaction records for manual review."""
    interactions_by_id = {
        r["interaction_id"]: r for r in rows if r.get("event") == "interaction" and r.get("interaction_id")
    }
    candidates: list[dict] = []
    for fb in rows:
        if fb.get("event") != "feedback" or fb.get("helpful") is not False:
            continue
        iid = fb.get("interaction_id")
        interaction = interactions_by_id.get(iid, {})
        candidates.append(
            {
                "interaction_id": iid,
                "timestamp": fb.get("timestamp") or interaction.get("timestamp"),
                "intent": interaction.get("intent"),
                "question": interaction.get("question"),
                "note": fb.get("note") or "",
                "raw_answer_snippet": (interaction.get("raw_answer") or "")[:500],
            }
        )
    candidates.sort(key=lambda r: r.get("timestamp") or "", reverse=True)
    return candidates


def print_negative_feedback_report(candidates: list[dict]):
    if not candidates:
        print("No negative feedback records found.")
        return

    by_intent: dict[str, list[dict]] = defaultdict(list)
    for row in candidates:
        by_intent[row.get("intent") or "?"].append(row)

    print(f"negative_feedback_count={len(candidates)}")
    print("by_intent:", {k: len(v) for k, v in sorted(by_intent.items())})
    print("\n--- review candidates (most recent first) ---")
    for row in candidates:
        intent = row.get("intent") or "?"
        question = (row.get("question") or "")[:120]
        note = row.get("note") or "(no note)"
        print(f"[{row.get('timestamp')}] intent={intent}")
        print(f"  Q: {question}")
        print(f"  Note: {note}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Summarize interactions.jsonl")
    parser.add_argument("--path", default="interactions.jsonl")
    parser.add_argument(
        "--negative-feedback-report",
        action="store_true",
        help="Export negative feedback joined to questions for manual review",
    )
    parser.add_argument(
        "--export-json",
        metavar="FILE",
        help="When used with --negative-feedback-report, write candidates to JSON",
    )
    args = parser.parse_args()

    rows = load_records(Path(args.path))
    if not rows:
        print(f"No records in {args.path}")
        return

    if args.negative_feedback_report:
        candidates = build_negative_feedback_report(rows)
        if args.export_json:
            Path(args.export_json).write_text(
                json.dumps(candidates, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            print(f"Wrote {len(candidates)} candidates to {args.export_json}")
        print_negative_feedback_report(candidates)
        return

    interactions = [r for r in rows if r.get("event") == "interaction"]
    feedback = [r for r in rows if r.get("event") == "feedback"]

    print(f"total_lines={len(rows)} interactions={len(interactions)} feedback={len(feedback)}")

    if interactions:
        parse_fail = sum(1 for r in interactions if not r.get("parsed_ok"))
        low_conf = sum(1 for r in interactions if r.get("confidence_int") is not None and r["confidence_int"] < 50)
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
