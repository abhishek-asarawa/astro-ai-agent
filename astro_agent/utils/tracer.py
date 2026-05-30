"""JSONL tracing for LLM calls and user interactions (opt-in via ASTRO_TRACE_ENABLED)."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from astro_agent.rag import config as cfg


def _trace_path() -> str:
    return os.getenv("ASTRO_TRACE_PATH", "traces.jsonl")


def _interaction_trace_path() -> str:
    return os.getenv("ASTRO_INTERACTION_TRACE_PATH", "interactions.jsonl")


def _tracing_enabled() -> bool:
    val = os.getenv("ASTRO_TRACE_ENABLED", "").strip().lower()
    return val in ("1", "true", "yes", "on")


def _store_raw_birth_in_traces() -> bool:
    val = os.getenv("ASTRO_TRACE_STORE_BIRTH", "").strip().lower()
    return val in ("1", "true", "yes", "on")


def _append_jsonl(path: str, record: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def chart_fingerprint(
    *,
    birth_date_iso: str,
    birth_time_iso: str,
    city_name: str,
) -> str:
    raw = f"{birth_date_iso}|{birth_time_iso}|{city_name.strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


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
        "event": "llm_call",
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
    _append_jsonl(_trace_path(), record)


def trace_interaction(
    *,
    interaction_id: str,
    session_id: str,
    question: str,
    raw_answer: str,
    displayed_answer: str,
    intent: str | None = None,
    model: str | None = None,
    latency_ms: float | None = None,
    rag_enabled: bool = False,
    agent_loop: bool = False,
    ref_ids: list[str] | None = None,
    confidence_int: int | None = None,
    parsed_ok: bool = False,
    birth_date_iso: str | None = None,
    birth_time_iso: str | None = None,
    city_name: str | None = None,
    **extra: Any,
) -> None:
    if not _tracing_enabled():
        return
    record: dict[str, Any] = {
        "event": "interaction",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "interaction_id": interaction_id,
        "session_id": session_id,
        "question": question,
        "raw_answer": raw_answer,
        "displayed_answer": displayed_answer,
        "intent": intent,
        "model": model,
        "latency_ms": round(float(latency_ms), 2) if latency_ms is not None else None,
        "rag_enabled": bool(rag_enabled),
        "agent_loop": bool(agent_loop),
        "ref_ids": list(ref_ids or []),
        "confidence_int": confidence_int,
        "parsed_ok": bool(parsed_ok),
    }
    if city_name:
        record["city_name"] = city_name.strip()
    if birth_date_iso and birth_time_iso:
        record["chart_fingerprint"] = chart_fingerprint(
            birth_date_iso=birth_date_iso,
            birth_time_iso=birth_time_iso,
            city_name=city_name or "",
        )
        if _store_raw_birth_in_traces():
            record["birth_date_ist"] = birth_date_iso
            record["birth_time_ist"] = birth_time_iso
    record.update(extra)
    _append_jsonl(_interaction_trace_path(), record)


def trace_feedback(
    *,
    interaction_id: str,
    session_id: str,
    helpful: bool,
    note: str | None = None,
    **extra: Any,
) -> None:
    if not _tracing_enabled():
        return
    record = {
        "event": "feedback",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "interaction_id": interaction_id,
        "session_id": session_id,
        "helpful": bool(helpful),
        "note": (note or "").strip() or None,
    }
    record.update(extra)
    _append_jsonl(_interaction_trace_path(), record)


def estimate_prompt_tokens(prompt: str | None) -> int:
    if not prompt:
        return 0
    return cfg.estimate_tokens(prompt)
