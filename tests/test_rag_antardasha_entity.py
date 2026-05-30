"""p3c: active Antardasha lord flows into RAG structural text and query entities."""

from astro_agent.rag.inject import _features_to_chart_facts
from astro_agent.rag.search import _query_entities, _summarize_chart_facts


def test_summarize_chart_facts_includes_antardasha_fragment():
    chart_facts = {
        "lagna": "Aries",
        "Sun": {"dignity": "[NEUTRAL]", "house": 5, "sign": "Leo"},
        "_antardasha_lord": "Venus",
    }
    s = _summarize_chart_facts(chart_facts)
    assert "Venus" in s
    assert "antardasha" in s.lower()
    assert "Vimshottari" in s


def test_query_entities_extracts_antardasha_planet():
    chart_facts = {
        "lagna": "Aries",
        "Sun": {"dignity": "[NEUTRAL]", "house": 5, "sign": "Leo"},
        "_antardasha_lord": "Venus",
    }
    entities = _query_entities("career and profession", chart_facts)
    assert "Venus" in entities


def test_features_to_chart_facts_sets_antardasha_meta():
    features = {
        "lagna": {"rashi": "Gemini"},
        "planets": {},
        "planetary_dignities": {},
        "active_antardasha": {
            "dasha": "Mars",
            "start": "2020-01-01",
            "end": "2021-01-01",
        },
    }
    cf = _features_to_chart_facts(features)
    assert cf.get("_antardasha_lord") == "Mars"
    assert "Mars antardasha" in _summarize_chart_facts(cf)
