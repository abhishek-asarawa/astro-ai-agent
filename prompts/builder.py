"""Domain prompt builders."""

from dashas import format_dasha_timeline
import rag_config as cfg
from chart_engine import (
    _render_dasha_section,
    _render_domain_signals,
    _render_functional_lords,
    _render_planet_strengths,
)


def _build_domain_prompt(
    features,
    user_question,
    domain_name,
    summary_label,
    risk_label,
    opportunity_label,
    signal_header,
    signal_house_map,
    prior_context=None,
):
    body = (
        f"You are an expert Vedic astrologer focused on {domain_name} prediction.\n"
        "Use only the provided computed data and avoid unsupported claims.\n"
    )
    if cfg.STRUCTURED_OUTPUT_ENABLED:
        body += (
            "Respond with JSON only matching this schema: "
            '{"summary": str, "evidence": [str], "risk": str, "opportunity": str, "confidence": int}.\n'
            "Put chart-based reasoning in evidence strings.\n\n"
        )
    else:
        body += (
            "Return output in this exact format:\n"
            f"{summary_label}: <3-5 lines>\n"
            "Evidence:\n"
            "- <signal 1>\n"
            "- <signal 2>\n"
            "- <signal 3>\n"
            f"{risk_label}: <short line>\n"
            f"{opportunity_label}: <short line>\n"
            "Confidence: <0-100 integer>\n\n"
        )
    body += (
        f"{signal_header}:\n"
        + _render_domain_signals(features, signal_house_map)
        + "\n\nPlanetStrengths:\n"
        + _render_planet_strengths(features)
        + "\n\nFunctionalLords:\n"
        + _render_functional_lords(features)
        + "\n\nCurrentDashas:\n"
        + _render_dasha_section(features)
        + "\n\n"
        + format_dasha_timeline(features["dasha_timeline"])
        + (f"\n\nPriorContext:\n{prior_context}" if prior_context else "")
        + f"\n\nQuestion: {user_question}"
    )
    return body


def build_career_prompt(features, user_question, prior_context=None):
    """Assemble deterministic, career-focused prompt sections."""
    return _build_domain_prompt(
        features=features,
        user_question=user_question,
        domain_name="CAREER",
        summary_label="CareerSummary",
        risk_label="CareerRisk",
        opportunity_label="CareerOpportunity",
        signal_header="CareerSignals",
        signal_house_map=[
            ("10th house lord", 10),
            ("6th house lord", 6),
            ("2nd house lord", 2),
            ("11th house lord", 11),
        ],
        prior_context=prior_context,
    )


def build_health_prompt(features, user_question, prior_context=None):
    return _build_domain_prompt(
        features=features,
        user_question=user_question,
        domain_name="HEALTH",
        summary_label="HealthSummary",
        risk_label="HealthRisk",
        opportunity_label="HealthOpportunity",
        signal_header="HealthSignals",
        signal_house_map=[
            ("1st house lord", 1),
            ("6th house lord", 6),
            ("8th house lord", 8),
            ("12th house lord", 12),
        ],
        prior_context=prior_context,
    )


def build_wealth_prompt(features, user_question, prior_context=None):
    return _build_domain_prompt(
        features=features,
        user_question=user_question,
        domain_name="WEALTH",
        summary_label="WealthSummary",
        risk_label="WealthRisk",
        opportunity_label="WealthOpportunity",
        signal_header="WealthSignals",
        signal_house_map=[
            ("2nd house lord", 2),
            ("11th house lord", 11),
            ("5th house lord", 5),
            ("9th house lord", 9),
        ],
        prior_context=prior_context,
    )


def build_family_prompt(features, user_question, prior_context=None):
    return _build_domain_prompt(
        features=features,
        user_question=user_question,
        domain_name="FAMILY",
        summary_label="FamilySummary",
        risk_label="FamilyRisk",
        opportunity_label="FamilyOpportunity",
        signal_header="FamilySignals",
        signal_house_map=[
            ("4th house lord", 4),
            ("7th house lord", 7),
            ("2nd house lord", 2),
            ("5th house lord", 5),
        ],
        prior_context=prior_context,
    )


def build_general_prompt(features, user_question, prior_context=None):
    return _build_domain_prompt(
        features=features,
        user_question=user_question,
        domain_name="GENERAL LIFE",
        summary_label="OverallSummary",
        risk_label="OverallRisk",
        opportunity_label="OverallOpportunity",
        signal_header="GeneralSignals",
        signal_house_map=[
            ("1st house lord", 1),
            ("4th house lord", 4),
            ("7th house lord", 7),
            ("10th house lord", 10),
        ],
        prior_context=prior_context,
    )


def build_prompt_for_intent(features, user_question, intent, prior_context=None):
    intent_map = {
        "career": build_career_prompt,
        "health": build_health_prompt,
        "wealth": build_wealth_prompt,
        "family": build_family_prompt,
        "general": build_general_prompt,
    }
    builder = intent_map.get((intent or "").strip().lower(), build_general_prompt)
    return builder(features, user_question, prior_context=prior_context)
