from response_sections import format_chat_answer_markdown, parse_structured_answer


SAMPLE = """OverallSummary: Love may feel delayed in this chapter of life.
Evidence:
- Romance sector looks strained right now.
- Current life period emphasizes work over dating.
OverallRisk: Watch for repeating old patterns.
OverallOpportunity: Friendships and hobbies can open new doors.
Confidence: 70
"""


def test_parse_structured_answer_template():
    parsed = parse_structured_answer(SAMPLE)
    assert parsed["parsed_ok"]
    assert parsed["summary"]
    assert parsed["confidence_int"] == 70


def test_format_chat_answer_markdown_sections():
    parsed = parse_structured_answer(SAMPLE)
    md = format_chat_answer_markdown(parsed, SAMPLE)
    assert "**In short**" in md
    assert "**What stands out**" in md
    assert "**What to be careful about**" in md
    assert "**What can help**" in md
    assert "70" in md


def test_format_chat_answer_fallback():
    md = format_chat_answer_markdown({"parsed_ok": False}, "Plain fallback text.")
    assert "Plain fallback" in md
