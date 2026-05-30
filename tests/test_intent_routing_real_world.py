import pytest

from astro_agent.routing.intent_router import detect_intent


@pytest.mark.parametrize(
    "question, expected",
    [
        ("Will I settle abroad permanently?", "career"),
        ("Will I inherit ancestral property?", "wealth"),
        ("When will I have children?", "family"),
        ("Will I have a son or daughter?", "family"),
        ("What kind of spouse will I have?", "family"),
        ("Will my father live long?", "family"),
        ("Is it a good time to change my job?", "career"),
        ("When will I get married?", "family"),
        ("Are there any health concerns in my chart?", "health"),
        ("When will my financial situation improve?", "wealth"),
        ("Which field of study suits me best?", "career"),
        ("What major life changes are coming up for me?", "general"),
        ("Should I start my own business?", "career"),
        ("Will I get a promotion this year?", "career"),
        ("What career am I most suited for?", "career"),
        ("Is my current partner compatible with me?", "family"),
        ("Why is my marriage getting delayed?", "family"),
        ("When will I recover from my illness?", "health"),
        ("Am I prone to stress or anxiety?", "health"),
        ("What health risks should I watch out for?", "health"),
        ("Should I invest in property now?", "wealth"),
        ("Which period is most favorable for me right now?", "general"),
    ],
)
def test_real_world_routing_rules(question, expected):
    result = detect_intent(question, model_name="unused")
    assert result["intent"] == expected
    assert result["method"] == "rules"


def test_golden_file_loads():
    from data.golden.schema import load_golden_cases

    cases = load_golden_cases("data/golden/real_world_questions_v0.json")
    assert len(cases) == 28
    assert all(c.question for c in cases)
    assert all(c.expected_intent for c in cases)
