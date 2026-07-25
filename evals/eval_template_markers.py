"""Shim: prefer ``astro_agent.utils.eval_template_markers`` / ``astro_agent.intents``."""

from astro_agent.intents import TEMPLATE_MARKERS
from astro_agent.utils.eval_template_markers import score_template_adherence

__all__ = ["TEMPLATE_MARKERS", "score_template_adherence"]
