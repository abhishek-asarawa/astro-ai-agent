#!/usr/bin/env python3
"""
Run and monitor PR1 acceptance checks with long-running command polling.

This script is designed for local execution where Ollama is available.
It runs each acceptance check sequentially, streams output to console,
writes per-check logs, and prints a final pass/fail summary.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List


@dataclass
class CheckResult:
    name: str
    passed: bool
    details: str
    log_path: str
    elapsed_s: float


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _run_command(
    name: str,
    cmd: List[str],
    cwd: Path,
    log_path: Path,
    poll_interval_s: int,
) -> tuple[int, str, float]:
    started = time.time()
    print(f"\n=== {name} ===")
    print(f"$ {' '.join(cmd)}")
    print(f"log: {log_path}")
    log_path.parent.mkdir(parents=True, exist_ok=True)

    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    all_lines: List[str] = []
    last_ping = time.time()
    with log_path.open("w", encoding="utf-8") as lf:
        while True:
            line = proc.stdout.readline() if proc.stdout else ""
            if line:
                print(line, end="")
                lf.write(line)
                lf.flush()
                all_lines.append(line)
                last_ping = time.time()
            elif proc.poll() is not None:
                break
            else:
                if (time.time() - last_ping) >= poll_interval_s:
                    print(
                        f"[watch] {name} still running... elapsed={int(time.time() - started)}s",
                        flush=True,
                    )
                    last_ping = time.time()
                time.sleep(0.5)

        if proc.stdout:
            tail = proc.stdout.read()
            if tail:
                print(tail, end="")
                lf.write(tail)
                all_lines.append(tail)

    elapsed = time.time() - started
    return proc.returncode, "".join(all_lines), elapsed


def _contains_ref_tag(text: str) -> bool:
    return bool(re.search(r"\[ref:[^\]]+\]", text))


def check_rag_on(
    repo: Path,
    logs_dir: Path,
    timeout_s: int,
    model_name: str,
    num_ctx: int,
    poll_interval_s: int,
) -> CheckResult:
    log_path = logs_dir / "01_rag_on.log"
    cmd = [
        "venv/bin/python",
        "astro_engine.py",
        "--rag-on",
        "--no-preview",
        "--model",
        model_name,
        "--num-ctx",
        str(num_ctx),
        "--timeout",
        str(timeout_s),
        "--question",
        "What is the professional outlook for this chart?",
    ]
    rc, output, elapsed = _run_command("Check 1: rag-on smoke", cmd, repo, log_path, poll_interval_s)
    passed = (
        rc == 0
        and "RAG mode: ON" in output
        and "refs=" in output
        and "[rag] retrieved=" in output
    )
    details = "RAG ON path executed with retrieval footer."
    if not passed:
        details = "Failed rag-on smoke expectations."
    return CheckResult("rag_on_smoke", passed, details, str(log_path), elapsed)


def check_rag_off(
    repo: Path,
    logs_dir: Path,
    timeout_s: int,
    model_name: str,
    num_ctx: int,
    poll_interval_s: int,
) -> CheckResult:
    log_path = logs_dir / "02_rag_off.log"
    cmd = [
        "venv/bin/python",
        "astro_engine.py",
        "--rag-off",
        "--no-preview",
        "--model",
        model_name,
        "--num-ctx",
        str(num_ctx),
        "--timeout",
        str(timeout_s),
        "--question",
        "What is the professional outlook for this chart?",
    ]
    rc, output, elapsed = _run_command("Check 2: rag-off smoke", cmd, repo, log_path, poll_interval_s)
    passed = rc == 0 and "RAG mode: OFF" in output and "[rag] retrieved=" not in output
    details = "RAG OFF path executed without retrieval footer."
    if not passed:
        details = "Failed rag-off smoke expectations."
    return CheckResult("rag_off_smoke", passed, details, str(log_path), elapsed)


def check_evaluate_career_rag(
    repo: Path,
    logs_dir: Path,
    timeout_s: int,
    model_name: str,
    num_ctx: int,
    workers: int,
    runs: int,
    poll_interval_s: int,
) -> CheckResult:
    log_path = logs_dir / "03_evaluate_career_rag.log"
    output_path = repo / "career_eval_report.json"
    cmd = [
        "venv/bin/python",
        "evaluate_career.py",
        "--rag",
        "--runs",
        str(runs),
        "--workers",
        str(workers),
        "--model",
        model_name,
        "--num-ctx",
        str(num_ctx),
        "--timeout",
        str(timeout_s),
        "--output",
        str(output_path),
        "--history",
        "eval_history.json",
        "--retention-mode",
        "rag",
        "--judge-model",
        "llama3.2:3b",
    ]
    rc, output, elapsed = _run_command(
        "Check 3: evaluate_career --rag",
        cmd,
        repo,
        log_path,
        poll_interval_s,
    )
    passed = rc == 0
    details = "evaluate_career completed."

    if output_path.exists():
        try:
            report = json.loads(output_path.read_text(encoding="utf-8"))
            summary = report.get("summary", {})
            rag_kw = summary.get("rag_enriched_keyword_avg")
            enr_kw = summary.get("enriched_keyword_avg")
            judge_avg = summary.get("rag_judge_grounding_avg")
            gmax = summary.get("rag_grounding_max_sim_avg")
            if judge_avg is not None:
                details = (
                    f"rag_judge_grounding_avg={judge_avg} rag_grounding_max_sim_avg={gmax} "
                    f"(keywords rag={rag_kw} enriched={enr_kw})"
                )
                if float(judge_avg) < 3.0:
                    passed = False
                    details = f"Regression (judge): {details}"
            elif gmax is not None:
                details = (
                    f"rag_grounding_max_sim_avg={gmax} (keywords rag={rag_kw} enriched={enr_kw})"
                )
                if float(gmax) < 0.3:
                    passed = False
                    details = f"Regression (grounding): {details}"
            elif rag_kw is not None and enr_kw is not None:
                details = f"rag_enriched_keyword_avg={rag_kw} vs enriched_keyword_avg={enr_kw} (no judge/grounding in summary)"
                if float(rag_kw) < float(enr_kw):
                    passed = False
                    details = f"Regression: {details}"
            else:
                passed = False
                details = "Missing summary fields for acceptance check."
        except Exception as exc:
            passed = False
            details = f"Could not parse career_eval_report.json: {exc}"
    else:
        passed = False
        details = "career_eval_report.json not found after evaluate_career run."

    if rc != 0:
        details = f"evaluate_career exited {rc}. {details}"

    return CheckResult("evaluate_career_rag", passed, details, str(log_path), elapsed)


def check_evaluate_rag(
    repo: Path,
    logs_dir: Path,
    poll_interval_s: int,
) -> CheckResult:
    log_path = logs_dir / "04_evaluate_rag.log"
    output_path = repo / "rag_eval_report.json"
    cmd = [
        "venv/bin/python",
        "evaluate_rag.py",
        "--golden",
        "data/golden/rag_eval_v0.json",
        "--output",
        str(output_path),
        "--history",
        "rag_eval_history.json",
        "--no-retention",
    ]
    rc, output, elapsed = _run_command("Check 4: evaluate_rag", cmd, repo, log_path, poll_interval_s)
    passed = rc == 0
    details = "evaluate_rag completed."
    if rc != 0:
        details = f"evaluate_rag exited {rc}."

    if output_path.exists():
        try:
            report = json.loads(output_path.read_text(encoding="utf-8"))
            summary = report.get("summary", {})
            gold = float(summary.get("rag_recall_at_3_gold", 0.0))
            silver = float(summary.get("rag_recall_at_5_silver", 0.0))
            delta = float(summary.get("rag_heuristic_delta", 0.0))
            details = f"gold@3={gold}, silver@5={silver}, delta={delta}"
        except Exception as exc:
            passed = False
            details = f"Could not parse rag_eval_report.json: {exc}"
    return CheckResult("evaluate_rag_regression", passed, details, str(log_path), elapsed)


def check_non_career_intent(
    repo: Path,
    logs_dir: Path,
    timeout_s: int,
    model_name: str,
    num_ctx: int,
    poll_interval_s: int,
) -> CheckResult:
    log_path = logs_dir / "05_non_career_rag_on.log"
    cmd = [
        "venv/bin/python",
        "astro_engine.py",
        "--rag-on",
        "--no-preview",
        "--model",
        model_name,
        "--num-ctx",
        str(num_ctx),
        "--timeout",
        str(timeout_s),
        "--question",
        "How is my health going to be next year?",
    ]
    rc, output, elapsed = _run_command("Check 5: non-career intent", cmd, repo, log_path, poll_interval_s)
    passed = rc == 0 and "intent=health" in output and "[rag] retrieved=" in output
    details = "Health intent routed with retrieval."
    if not passed:
        details = "Failed to confirm health intent routing / retrieval footer."
    return CheckResult("non_career_intent_route", passed, details, str(log_path), elapsed)


def print_summary(results: List[CheckResult]) -> int:
    print("\n=== PR1 Acceptance Summary ===")
    failed = 0
    for idx, r in enumerate(results, start=1):
        status = "PASS" if r.passed else "FAIL"
        if not r.passed:
            failed += 1
        print(
            f"{idx}. {r.name}: {status} | {r.details} | "
            f"elapsed={r.elapsed_s:.1f}s | log={r.log_path}"
        )
    print(f"\nTotal: {len(results)} checks, {failed} failed.")
    return 1 if failed else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run and watch PR1 acceptance checks with polling output."
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="Repo root path (default: current directory).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="Timeout seconds passed to astro/eval commands (default: 180).",
    )
    parser.add_argument(
        "--model",
        default="deepseek-r1:14b",
        help="Model name for astro/eval checks (default: deepseek-r1:14b).",
    )
    parser.add_argument(
        "--num-ctx",
        type=int,
        default=16384,
        help="Context window for astro/eval checks (default: 16384).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Workers for evaluate_career --rag (default: 1).",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=2,
        help="Runs for evaluate_career --rag (default: 2).",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=20,
        help="Heartbeat seconds for long-running checks (default: 20).",
    )
    parser.add_argument(
        "--logs-dir",
        default="acceptance_logs",
        help="Directory for check logs (default: acceptance_logs).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = Path(args.repo).resolve()
    if not (repo / "astro_engine.py").exists():
        print(f"Repo path looks wrong: {repo}", file=sys.stderr)
        return 2

    logs_dir = repo / args.logs_dir / _now_stamp()
    os.environ.setdefault("PYTHONUNBUFFERED", "1")

    checks = [
        lambda: check_rag_on(
            repo, logs_dir, args.timeout, args.model, args.num_ctx, args.poll_interval
        ),
        lambda: check_rag_off(
            repo, logs_dir, args.timeout, args.model, args.num_ctx, args.poll_interval
        ),
        lambda: check_evaluate_career_rag(
            repo,
            logs_dir,
            args.timeout,
            args.model,
            args.num_ctx,
            args.workers,
            args.runs,
            args.poll_interval,
        ),
        lambda: check_evaluate_rag(repo, logs_dir, args.poll_interval),
        lambda: check_non_career_intent(
            repo, logs_dir, args.timeout, args.model, args.num_ctx, args.poll_interval
        ),
    ]

    results: List[CheckResult] = []
    for run_check in checks:
        result = run_check()
        results.append(result)

    return print_summary(results)


if __name__ == "__main__":
    raise SystemExit(main())
