"""Tests for the consultation service (mocked LLM / agent)."""

from unittest.mock import patch

from astro_agent.service.consultation import ConsultationRequest, run_consultation
from tests.fixtures.minimal_chart_features import MINIMAL_FEATURES


@patch("astro_agent.service.consultation.humanize_answer", side_effect=lambda raw, q, **kw: f"HUMAN:{raw[:40]}")
@patch(
    "astro_agent.service.consultation.query_ollama_once",
    return_value="CareerSummary: Good.\nEvidence:\n- x\nConfidence: 70",
)
@patch(
    "astro_agent.service.consultation.detect_intent",
    return_value={"intent": "career", "method": "rules", "confidence": 1.0},
)
@patch("astro_agent.service.consultation.build_chart_features", return_value=MINIMAL_FEATURES)
def test_run_consultation_linear_path(_chart, _intent, _ollama, _humanize):
    result = run_consultation(
        ConsultationRequest(
            year=1990,
            month=5,
            day=15,
            hour=10,
            minute=30,
            city_name="bengaluru",
            question="What career am I most suited for?",
            rag_enabled=False,
            agent_loop_enabled=False,
            timeout_s=30,
        )
    )
    assert result.ok
    assert result.intent_info["intent"] == "career"
    assert "CareerSummary" in result.raw_answer or "Good" in result.raw_answer
    assert result.displayed_answer.startswith("HUMAN:")
    assert result.interaction_id


@patch("astro_agent.service.consultation.run_agent_loop")
@patch("astro_agent.service.consultation.humanize_answer", side_effect=lambda raw, q, **kw: raw)
@patch(
    "astro_agent.service.consultation.detect_intent",
    return_value={"intent": "career", "method": "rules", "confidence": 1.0},
)
@patch("astro_agent.service.consultation.build_chart_features", return_value=MINIMAL_FEATURES)
def test_run_consultation_agent_path(_chart, _intent, _humanize, mock_agent):
    mock_agent.return_value = {
        "answer": "Agent answer",
        "method": "agent",
        "tool_calls_made": ["build_chart"],
        "error": None,
    }
    result = run_consultation(
        ConsultationRequest(
            year=1990,
            month=5,
            day=15,
            hour=10,
            minute=30,
            city_name="bengaluru",
            question="How is my career?",
            rag_enabled=True,
            agent_loop_enabled=True,
            timeout_s=30,
        )
    )
    assert result.ok
    assert result.method == "agent"
    assert result.raw_answer == "Agent answer"
    mock_agent.assert_called_once()
