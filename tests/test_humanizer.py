from unittest.mock import patch

from astro_agent.llm.humanizer import humanize_answer

SAMPLE_RAW = """OverallSummary: Your chart shows mixed signals for intimacy.
Evidence:
- Venus is in a private sign.
OverallRisk: Avoid shutting down emotionally.
OverallOpportunity: Honest talks can help.
OverallRemedies:
- Share feelings with your partner regularly.
Confidence: 65
"""


@patch("astro_agent.llm.humanizer.query_ollama_once")
def test_humanize_answer_uses_llm_response(mock_query):
    mock_query.return_value = (
        "Intimacy may feel uneven right now because Venus sits in a more private part of your chart. "
        "Try opening up to your partner about what you need."
    )
    result = humanize_answer(SAMPLE_RAW, "Why am I not satisfied with my sex life?")
    assert "Venus" in result
    assert "Summary:" not in result
    mock_query.assert_called_once()
    prompt = mock_query.call_args[0][0]
    assert "Do not use section headers" in prompt
    assert "Why am I not satisfied with my sex life?" in prompt


@patch("astro_agent.llm.humanizer.query_ollama_once")
def test_humanize_answer_falls_back_on_empty(mock_query):
    mock_query.return_value = ""
    result = humanize_answer(SAMPLE_RAW, "Why am I not satisfied with my sex life?")
    assert "mixed signals" in result or "Venus" in result
    assert "Summary:" not in result


@patch("astro_agent.llm.humanizer.query_ollama_once")
def test_humanize_answer_falls_back_on_short(mock_query):
    mock_query.return_value = "Too short."
    result = humanize_answer(SAMPLE_RAW, "test question")
    assert len(result) > 20
