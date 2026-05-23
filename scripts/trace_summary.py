#!/usr/bin/env python3
"""Summarize ASTRO JSONL trace logs."""

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean


def _parse_ts(raw):
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def load_records(path, hours=None):
    cutoff = None
    if hours is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = _parse_ts(rec.get("timestamp"))
        if cutoff and ts and ts < cutoff:
            continue
        rows.append(rec)
    return rows


def main():
    parser = argparse.ArgumentParser(description="Summarize traces.jsonl")
    parser.add_argument("--path", default="traces.jsonl")
    parser.add_argument("--last", type=float, default=None, dest="last_hours", help="Only last N hours")
    args = parser.parse_args()

    rows = load_records(args.path, hours=args.last_hours)
    if not rows:
        print(f"No records in {args.path}")
        return

    latencies = [r["latency_ms"] for r in rows if r.get("latency_ms") is not None]
    latencies.sort()
    p50 = latencies[len(latencies) // 2] if latencies else 0
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0

    by_model = {}
    for r in rows:
        by_model[r.get("model", "?")] = by_model.get(r.get("model", "?"), 0) + 1

    rag_on = sum(1 for r in rows if r.get("rag_active"))
    hall = [r.get("hallucinated_refs", 0) for r in rows]

    print(f"records={len(rows)}")
    print(f"latency_ms p50={p50:.1f} p95={p95:.1f} mean={mean(latencies):.1f}" if latencies else "latency_ms n/a")
    print(f"rag_active_calls={rag_on}")
    print(f"mean_hallucinated_refs={mean(hall):.2f}" if hall else "mean_hallucinated_refs=0")
    print("by_model:", by_model)


if __name__ == "__main__":
    main()
