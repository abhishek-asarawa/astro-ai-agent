"""Shared template adherence markers for eval harnesses."""

TEMPLATE_MARKERS = {
    "career": ["careersummary:", "evidence:", "careerrisk:", "careeropportunity:", "confidence:"],
    "health": ["healthsummary:", "evidence:", "healthrisk:", "healthopportunity:", "confidence:"],
    "wealth": ["wealthsummary:", "evidence:", "wealthrisk:", "wealthopportunity:", "confidence:"],
    "family": ["familysummary:", "evidence:", "familyrisk:", "familyopportunity:", "confidence:"],
    "general": ["overallsummary:", "evidence:", "overallrisk:", "overallopportunity:", "confidence:"],
}


def score_template_adherence(text, intent):
    markers = TEMPLATE_MARKERS.get((intent or "general").strip().lower(), TEMPLATE_MARKERS["general"])
    if not (text or "").strip():
        return 0.0
    lower = text.lower()
    hits = sum(1 for marker in markers if marker in lower)
    return hits / len(markers)
