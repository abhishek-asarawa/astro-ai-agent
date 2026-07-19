"""Tests for sub-topic signal augmentation in domain prompts."""

from astro_agent.llm.prompts.builder import build_family_prompt


def _minimal_features():
    return {
        "lagna": {"rashi": "Gemini"},
        "planets": {
            "Venus": {"rashi": "Scorpio", "degrees": 17.83, "nakshatra": "Jyeshtha"},
            "Mars": {"rashi": "Virgo", "degrees": 3.52, "nakshatra": "Uttara Phalguni"},
            "Moon": {"rashi": "Cancer", "degrees": 0.33, "nakshatra": "Punarvasu"},
        },
        "planetary_dignities": {
            "Venus": "[Neutral]",
            "Mars": "[Neutral]",
            "Moon": "[Own Sign / Swakshetra, very strong]",
        },
        "house_lordships": {
            "Venus": [1, 6],
            "Mars": [7, 12],
            "Moon": [3],
        },
        "active_dasha": {"dasha": "Saturn", "start": "2020-01-01", "end": "2039-01-01"},
        "next_dasha": {"dasha": "Mercury", "start": "2039-01-01", "end": "2056-01-01"},
        "active_antardasha": {"dasha": "Venus", "start": "2024-01-01", "end": "2027-01-01"},
        "next_antardasha": {"dasha": "Sun", "start": "2027-01-01", "end": "2028-01-01"},
        "dasha_timeline": [],
    }


def test_intimacy_question_includes_subtopic_signals():
    prompt = build_family_prompt(
        _minimal_features(),
        "Why am I not satisfied with my sex life?",
    )
    assert "SubTopicSignals:" in prompt
    assert "8th house lord (intimacy/shared resources)" in prompt
    assert "12th house lord (bed comfort/privacy)" in prompt
    assert "Venus:" in prompt
    assert "Mars:" in prompt
    assert "FamilyRemedies:" in prompt


def test_non_intimacy_question_omits_subtopic_signals():
    prompt = build_family_prompt(
        _minimal_features(),
        "When will I get married?",
    )
    assert "SubTopicSignals:" not in prompt
