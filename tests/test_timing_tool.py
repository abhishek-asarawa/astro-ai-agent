"""Tests for timing horizon parsing, dasha transition reports, and agent wiring."""

import datetime
import json

import pytest

from astro_agent.agent.loop import _dispatch_tool
from astro_agent.chart.engine import build_chart_features
from astro_agent.chart.timing import (
    build_timing_report,
    format_timing_context_block,
    parse_horizon,
    question_has_time_horizon,
)
from astro_agent.llm.prompts.builder import build_career_prompt

ANCHOR = datetime.date(2026, 5, 31)


@pytest.mark.parametrize(
    ("text", "expected_start", "expected_end"),
    [
        ("Will I get promotion in next 6 months?", ANCHOR, datetime.date(2026, 11, 30)),
        ("Any change in coming 6 days?", ANCHOR, datetime.date(2026, 6, 6)),
        ("What happens this year?", ANCHOR, datetime.date(2026, 12, 31)),
        ("Outlook for next year?", datetime.date(2027, 1, 1), datetime.date(2027, 12, 31)),
        ("How is the half year looking?", ANCHOR, datetime.date(2026, 11, 30)),
        ("Will six months bring change?", ANCHOR, datetime.date(2026, 11, 30)),
        ("When will I get married?", ANCHOR, datetime.date(2027, 5, 31)),
        ("What major life changes are coming up for me?", ANCHOR, datetime.date(2027, 5, 31)),
        ("Which period is most favorable for me right now?", ANCHOR, datetime.date(2027, 5, 31)),
    ],
)
def test_parse_horizon_common_phrases(text, expected_start, expected_end):
    start, end = parse_horizon(text, ANCHOR)
    assert start == expected_start
    assert end == expected_end


def test_question_has_time_horizon():
    assert question_has_time_horizon("Will I get promotion in next 6 months?")
    assert question_has_time_horizon("When will I recover from my illness?")
    assert not question_has_time_horizon("What career am I suited for?")


def test_build_timing_report_includes_near_term_checkpoint():
    features = build_chart_features(1990, 5, 15, 10, 30, "bengaluru", as_of_date=ANCHOR)
    report = build_timing_report(
        features,
        window_text="next 6 months",
        as_of_date=ANCHOR,
    )
    assert report["horizon_days"] > 6
    assert report["near_term_6_day"] is not None
    assert report["near_term_6_day"]["horizon_days"] == 6
    assert "active_mahadasha" in report
    assert "active_antardasha" in report


def test_build_timing_report_recomputes_from_timeline_not_stale_snapshot():
    features = build_chart_features(1990, 5, 15, 10, 30, "bengaluru", as_of_date=ANCHOR)
    past = datetime.date(2015, 1, 1)
    report = build_timing_report(features, window_text="next 6 months", as_of_date=past)
    assert report["as_of_date"] == past.isoformat()
    assert report["active_mahadasha"] is not None
    assert report["active_mahadasha"]["start"] <= past.isoformat()


def test_transition_detection_across_mahadasha_boundary():
    timeline = [
        {"dasha": "Sun", "start": "2026-01-01", "end": "2026-06-15", "is_birth_dasha": False},
        {"dasha": "Moon", "start": "2026-06-15", "end": "2036-06-15", "is_birth_dasha": False},
    ]
    features = {"dasha_timeline": timeline}
    report = build_timing_report(
        features,
        start_date="2026-05-01",
        end_date="2026-08-01",
        as_of_date=datetime.date(2026, 5, 1),
    )
    transition_types = {t["type"] for t in report["transitions"]}
    assert "mahadasha" in transition_types
    assert any(t["lord"] == "Moon" for t in report["transitions"])


def test_as_of_date_passthrough_in_build_chart_features():
    anchor = datetime.date(2015, 1, 1)
    features = build_chart_features(1990, 5, 15, 10, 30, "bengaluru", as_of_date=anchor)
    active = features["active_dasha"]
    assert active is not None
    start = datetime.date.fromisoformat(active["start"])
    end = datetime.date.fromisoformat(active["end"])
    assert start <= anchor <= end


def test_dispatch_get_timing_window_returns_json():
    features = build_chart_features(1992, 1, 11, 8, 45, "mumbai", as_of_date=ANCHOR)
    raw = _dispatch_tool(
        "get_timing_window",
        {"window_text": "next 6 months", "as_of_date": ANCHOR.isoformat()},
        features,
        timeout_s=30,
    )
    report = json.loads(raw)
    for key in (
        "as_of_date",
        "window_start",
        "window_end",
        "horizon_days",
        "active_mahadasha",
        "active_antardasha",
        "days_until_antardasha_end",
        "days_until_mahadasha_end",
        "transitions",
        "near_term_6_day",
    ):
        assert key in report


def test_linear_prompt_injects_timing_context_for_horizon_question():
    features = build_chart_features(1992, 1, 11, 8, 45, "mumbai", as_of_date=ANCHOR)
    prompt = build_career_prompt(features, "Will I get promotion in next 6 months?")
    assert "TimingContext:" in prompt
    assert "TimingAnswerRules:" in prompt
    assert "Timing window:" in prompt
    assert "PromotionAnswerRules:" in prompt
    assert "10th house/status" in prompt
    assert "DaysUntilAntardashaEnd:" in prompt
    assert "WindowEnd:" in prompt


def test_linear_prompt_skips_timing_context_without_horizon():
    features = build_chart_features(1992, 1, 11, 8, 45, "mumbai", as_of_date=ANCHOR)
    prompt = build_career_prompt(features, "What career am I suited for?")
    assert "TimingContext:" not in prompt


def test_format_timing_context_block_is_compact():
    report = build_timing_report(
        {"dasha_timeline": []},
        start_date="2026-05-31",
        end_date="2026-11-30",
        as_of_date=ANCHOR,
    )
    block = format_timing_context_block(report)
    assert block.startswith("TimingContext:")
    assert "TimingInstruction:" in block
    assert "TodayDate: 2026-05-31" in block
