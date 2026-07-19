"""Unit tests for agent loop dispatch, turn limits, and linear fallback."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tests.fixtures.minimal_chart_features import MINIMAL_FEATURES


def test_dispatch_build_chart():
    from astro_agent.agent.loop import _dispatch_tool

    result = _dispatch_tool("build_chart", {}, MINIMAL_FEATURES, timeout_s=30)
    assert "Lagna:" in result
    assert "Mars:" in result or "Sun:" in result


def test_dispatch_get_dasha():
    from astro_agent.agent.loop import _dispatch_tool

    result = _dispatch_tool("get_dasha", {}, MINIMAL_FEATURES, timeout_s=30)
    assert "Active Mahadasha" in result
    assert "Jupiter" in result


def test_dispatch_unknown_tool():
    from astro_agent.agent.loop import _dispatch_tool

    result = _dispatch_tool("not_a_tool", {}, MINIMAL_FEATURES, timeout_s=30)
    assert "Unknown tool" in result


def test_dispatch_detect_intent():
    from astro_agent.agent.loop import _dispatch_tool

    result = _dispatch_tool(
        "detect_intent",
        {"question": "Will I get a promotion this year?"},
        MINIMAL_FEATURES,
        timeout_s=30,
    )
    assert "career" in result


def test_dispatch_get_timing_window_returns_json():
    from astro_agent.agent.loop import _dispatch_tool

    result = _dispatch_tool(
        "get_timing_window",
        {"window_text": "next 6 months", "as_of_date": "2025-01-01"},
        MINIMAL_FEATURES,
        timeout_s=30,
    )
    assert "window" in result.lower() or "Window" in result or "{" in result


@patch("astro_agent.agent.loop._call_ollama_chat")
@patch("astro_agent.agent.loop._linear_fallback")
def test_agent_loop_falls_back_when_chat_fails(mock_fallback, mock_chat):
    from astro_agent.agent.loop import run_agent_loop

    mock_chat.return_value = None
    mock_fallback.return_value = "fallback answer"

    result = run_agent_loop(
        user_question="How is my career?",
        features=MINIMAL_FEATURES,
        intent="career",
        model_name="test-model",
        timeout_s=30,
        num_ctx=2048,
        rag_enabled=False,
    )
    assert result["method"] == "linear_fallback"
    assert result["answer"] == "fallback answer"
    mock_fallback.assert_called_once()


@patch("astro_agent.agent.loop._call_ollama_chat")
def test_agent_loop_returns_final_answer_without_tools(mock_chat):
    from astro_agent.agent.loop import run_agent_loop

    mock_chat.return_value = {
        "message": {
            "content": "CareerSummary: Strong period ahead.\nEvidence:\n- Point\nConfidence: 70",
            "tool_calls": [],
        }
    }

    result = run_agent_loop(
        user_question="How is my career?",
        features=MINIMAL_FEATURES,
        intent="career",
        model_name="test-model",
        timeout_s=30,
        num_ctx=2048,
        rag_enabled=False,
    )
    assert result["method"] == "agent"
    assert "CareerSummary" in result["answer"] or "Strong period" in result["answer"]
    assert result["tool_calls_made"] == []


@patch("astro_agent.agent.loop._call_ollama_chat")
@patch("astro_agent.agent.loop._linear_fallback")
@patch("astro_agent.agent.loop.MAX_AGENT_TURNS", 1)
def test_agent_loop_turn_limit_triggers_fallback(mock_fallback, mock_chat):
    from astro_agent.agent.loop import run_agent_loop

    mock_chat.return_value = {
        "message": {
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "build_chart",
                        "arguments": {},
                    }
                }
            ],
        }
    }
    mock_fallback.return_value = "turn-limit fallback"

    result = run_agent_loop(
        user_question="How is my career?",
        features=MINIMAL_FEATURES,
        intent="career",
        model_name="test-model",
        timeout_s=30,
        num_ctx=2048,
        rag_enabled=False,
    )
    assert result["method"] == "linear_fallback"
    assert "build_chart" in result["tool_calls_made"]
    assert result["answer"] == "turn-limit fallback"
