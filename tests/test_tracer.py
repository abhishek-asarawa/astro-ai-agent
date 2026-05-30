import json
import os

from astro_agent.utils.tracer import chart_fingerprint, trace_feedback, trace_interaction, trace_llm_call


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


def test_trace_interaction_disabled_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("ASTRO_TRACE_ENABLED", raising=False)
    path = tmp_path / "interactions.jsonl"
    monkeypatch.setenv("ASTRO_INTERACTION_TRACE_PATH", str(path))
    trace_interaction(
        interaction_id="abc",
        session_id="sess",
        question="Why love?",
        raw_answer="raw",
        displayed_answer="display",
    )
    assert not path.exists()


def test_trace_interaction_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTRO_TRACE_ENABLED", "1")
    path = tmp_path / "interactions.jsonl"
    monkeypatch.setenv("ASTRO_INTERACTION_TRACE_PATH", str(path))
    trace_interaction(
        interaction_id="abc",
        session_id="sess",
        question="Why love?",
        raw_answer="raw",
        displayed_answer="display",
        birth_date_iso="1998-09-27",
        birth_time_iso="13:00",
        city_name="delhi",
    )
    rec = json.loads(path.read_text(encoding="utf-8").strip())
    assert rec["event"] == "interaction"
    assert rec["question"] == "Why love?"
    assert rec["chart_fingerprint"] == chart_fingerprint(
        birth_date_iso="1998-09-27",
        birth_time_iso="13:00",
        city_name="delhi",
    )
    assert "birth_date_ist" not in rec


def test_trace_feedback_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTRO_TRACE_ENABLED", "1")
    path = tmp_path / "interactions.jsonl"
    monkeypatch.setenv("ASTRO_INTERACTION_TRACE_PATH", str(path))
    trace_feedback(interaction_id="abc", session_id="sess", helpful=True, note="great")
    rec = json.loads(path.read_text(encoding="utf-8").strip())
    assert rec["event"] == "feedback"
    assert rec["helpful"] is True
    assert rec["note"] == "great"
