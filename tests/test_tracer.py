import json
import os

from tracer import trace_llm_call


def test_trace_disabled_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("ASTRO_TRACE_ENABLED", raising=False)
    path = tmp_path / "t.jsonl"
    monkeypatch.setenv("ASTRO_TRACE_PATH", str(path))
    trace_llm_call(model="m", latency_ms=10.0)
    assert not path.exists()


def test_trace_enabled_appends_jsonl(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTRO_TRACE_ENABLED", "1")
    path = tmp_path / "t.jsonl"
    monkeypatch.setenv("ASTRO_TRACE_PATH", str(path))
    trace_llm_call(model="qwen", latency_ms=42.5, intent="career", rag_active=True, ref_count=3)
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["model"] == "qwen"
    assert rec["latency_ms"] == 42.5
    assert rec["intent"] == "career"
    assert rec["rag_active"] is True
