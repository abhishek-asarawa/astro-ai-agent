from astro_agent.utils.response_sections import format_chat_answer_fallback, parse_structured_answer

SAMPLE = """OverallSummary: Love may feel delayed in this chapter of life.
Evidence:
- Romance sector looks strained right now.
- Current life period emphasizes work over dating.
OverallRisk: Watch for repeating old patterns.
OverallOpportunity: Friendships and hobbies can open new doors.
OverallRemedies:
- Be open about what you need from a partner.
- Schedule regular time for connection without distractions.
Confidence: 70
"""


def test_parse_structured_answer_template():
    parsed = parse_structured_answer(SAMPLE)
    assert parsed["parsed_ok"]
    assert parsed["summary"]
    assert parsed["confidence_int"] == 70
    assert len(parsed.get("remedies") or []) == 2


def test_format_chat_answer_fallback_sections():
    parsed = parse_structured_answer(SAMPLE)
    md = format_chat_answer_fallback(parsed, SAMPLE)
    assert "Love may feel delayed" in md
    assert "**Key points**" in md
    assert "**Cautions**" in md
    assert "**Upside**" in md
    assert "**Practical steps**" in md
    assert "70" not in md


def test_format_chat_answer_fallback():
    md = format_chat_answer_fallback({"parsed_ok": False}, "Plain fallback text.")
    assert "Plain fallback" in md
