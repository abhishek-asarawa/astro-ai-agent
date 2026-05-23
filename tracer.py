"""JSONL tracing for LLM calls (opt-in via ASTRO_TRACE_ENABLED)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import rag_config as cfg

def _trace_path() -> str:
    return os.getenv("ASTRO_TRACE_PATH", "traces.jsonl")


def _tracing_enabled() -> bool:
    val = os.getenv("ASTRO_TRACE_ENABLED", "").strip().lower()
    return val in ("1", "true", "yes", "on")


def trace_llm_call(
    *,
    model: str,
    latency_ms: float,
    intent: str | None = None,
    prompt_tokens_est: int | None = None,
    rag_active: bool = False,
    ref_count: int = 0,
    hallucinated_refs: int = 0,
    template_score: float | None = None,
    stage: str = "generate",
    **extra: Any,
) -> None:
    if not _tracing_enabled():
        return
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "intent": intent,
        "prompt_tokens_est": prompt_tokens_est,
        "latency_ms": round(float(latency_ms), 2),
        "rag_active": bool(rag_active),
        "ref_count": int(ref_count),
        "hallucinated_refs": int(hallucinated_refs),
        "template_score": template_score,
        "stage": stage,
    }
    record.update(extra)
    path = Path(_trace_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def estimate_prompt_tokens(prompt: str | None) -> int:
    if not prompt:
        return 0
    return cfg.estimate_tokens(prompt)
