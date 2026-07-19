"""Shared template adherence markers for eval harnesses."""

from astro_agent.intents import TEMPLATE_MARKERS


def score_template_adherence(text, intent):
    markers = TEMPLATE_MARKERS.get((intent or "general").strip().lower(), TEMPLATE_MARKERS["general"])
    if not (text or "").strip():
        return 0.0
    lower = text.lower()
    hits = sum(1 for marker in markers if marker in lower)
    return hits / len(markers)
