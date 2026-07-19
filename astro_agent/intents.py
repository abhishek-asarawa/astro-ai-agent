"""Single source of truth for supported intents and keyword banks.

Router rules, RAG ingest tags, prompt builders, and eval template markers
must all agree with ``SUPPORTED_INTENTS``. Call ``validate_intent_registry()``
from tests (and optionally at import) to catch partial rollouts.
"""

from __future__ import annotations

SUPPORTED_INTENTS = ("career", "health", "wealth", "family", "general")

# Keywords used by the hybrid intent *router* (user questions).
ROUTER_INTENT_KEYWORDS: dict[str, list[str]] = {
    "career": [
        "career", "job", "change job", "profession", "work", "promotion", "growth", "role",
        "employment", "10th lord", "tenth lord", "10th house", "tenth house", "10th", "tenth",
        "karma yogi", "livelihood", "fame", "occupation", "business", "vocation",
        "foreign settlement", "settle abroad", "visa", "migration", "abroad",
        "competitive exam", "higher studies", "study", "studies", "college", "admission",
        "education", "field of study",
    ],
    "health": [
        "health", "disease", "diseases", "illness", "ailment", "ailments", "medical",
        "fitness", "injury", "wellness", "recovery", "longevity", "long life", "lifespan",
        "8th lord", "8th house", "eighth house", "kendra", "afflicted",
    ],
    "wealth": [
        "wealth", "money", "finance", "financial", "income", "salary", "investment",
        "savings", "property", "ancestral property", "inheritance", "multiple income",
        "gains", "prosperity", "loan", "loans", "debt", "repay",
    ],
    "family": [
        "family", "marriage", "married", "spouse", "wife", "husband", "relationship",
        "parents", "father", "mother", "children", "child", "son", "daughter",
        "sibling", "siblings", "home", "domestic", "home life", "navamsa",
        "navamamsha", "navamsha", "twelfth lord", "12th lord", "progeny", "offspring",
        "9th lord", "ninth lord", "9th house", "ninth house", "fortunes", "pilgrimage",
    ],
    "general": [
        "overall", "general", "life", "future", "outlook", "summary", "holistic",
        "life purpose", "dharma", "fortune", "karma", "major life", "favorable period",
    ],
}

# Keywords used at RAG *ingest* to tag classical corpus chunks (book language).
RAG_INTENT_KEYWORDS: dict[str, list[str]] = {
    "career": [
        "career", "profession", "professional", "work", "works", "employment",
        "occupation", "livelihood", "deed", "deeds", "duties", "duty",
        "karma", "rajya", "authority", "position", "office",
        "business", "trade", "governmental", "royal patronage",
        "actions", "action",
    ],
    "wealth": [
        "wealth", "wealthy", "money", "finance", "financial", "income",
        "gain", "gains", "robes", "ornaments", "precious", "prosperity",
        "affluence", "dhana", "fortune", "fortunes", "rich",
    ],
    "health": [
        "health", "disease", "diseases", "illness", "ulcer", "bruises",
        "leprosy", "longevity", "long life", "lifespan", "ayur", "fear",
        "ailment", "ailments", "sick", "8th lord", "8th house", "eighth house",
        "kendra", "afflicted",
    ],
    "family": [
        "family", "marriage", "spouse", "wife", "husband", "children",
        "child", "putra", "parent", "father", "mother", "brother",
        "sister", "kin", "kindred", "domestic",
    ],
    "general": [
        "fame", "famous", "name", "honour", "honor", "happiness",
        "nature", "character", "personality", "life", "outlook",
    ],
}

# Eval template section markers (lowercase) per domain.
TEMPLATE_MARKERS: dict[str, list[str]] = {
    "career": ["careersummary:", "evidence:", "careerrisk:", "careeropportunity:", "careerremedies:", "confidence:"],
    "health": ["healthsummary:", "evidence:", "healthrisk:", "healthopportunity:", "healthremedies:", "confidence:"],
    "wealth": ["wealthsummary:", "evidence:", "wealthrisk:", "wealthopportunity:", "wealthremedies:", "confidence:"],
    "family": ["familysummary:", "evidence:", "familyrisk:", "familyopportunity:", "familyremedies:", "confidence:"],
    "general": ["overallsummary:", "evidence:", "overallrisk:", "overallopportunity:", "overallremedies:", "confidence:"],
}

# Prompt builder function names expected in llm.prompts.builder (validated in tests).
PROMPT_BUILDER_NAMES: dict[str, str] = {
    "career": "build_career_prompt",
    "health": "build_health_prompt",
    "wealth": "build_wealth_prompt",
    "family": "build_family_prompt",
    "general": "build_general_prompt",
}


def validate_intent_registry() -> list[str]:
    """Return a list of human-readable problems, empty if the registry is consistent."""
    problems: list[str] = []
    for intent in SUPPORTED_INTENTS:
        if intent not in ROUTER_INTENT_KEYWORDS:
            problems.append(f"missing ROUTER_INTENT_KEYWORDS[{intent!r}]")
        if intent not in RAG_INTENT_KEYWORDS:
            problems.append(f"missing RAG_INTENT_KEYWORDS[{intent!r}]")
        if intent not in TEMPLATE_MARKERS:
            problems.append(f"missing TEMPLATE_MARKERS[{intent!r}]")
        if intent not in PROMPT_BUILDER_NAMES:
            problems.append(f"missing PROMPT_BUILDER_NAMES[{intent!r}]")

    for bank_name, bank in (
        ("ROUTER_INTENT_KEYWORDS", ROUTER_INTENT_KEYWORDS),
        ("RAG_INTENT_KEYWORDS", RAG_INTENT_KEYWORDS),
        ("TEMPLATE_MARKERS", TEMPLATE_MARKERS),
        ("PROMPT_BUILDER_NAMES", PROMPT_BUILDER_NAMES),
    ):
        for key in bank:
            if key not in SUPPORTED_INTENTS:
                problems.append(f"{bank_name} has unknown intent {key!r}")
    return problems
