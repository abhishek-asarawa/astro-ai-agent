"""Domain prompt builders."""

import re

from astro_agent.chart.dashas import format_dasha_timeline
from astro_agent.chart.timing import build_timing_report, format_timing_context_block, question_has_time_horizon
from astro_agent.rag import config as cfg
from astro_agent.chart.engine import (
    _get_house_lord_for_house,
    _render_dasha_section,
    _render_domain_signals,
    _render_functional_lords,
    _render_planet_strengths,
)

_PLAIN_LANGUAGE_RULES = (
    "Write for a curious non-expert. Use warm, clear English.\n"
    "Avoid unexplained jargon: do not use bare labels like '5th lord', 'debilitated', "
    "'trik house', 'Vimshottari', 'Mahadasha', or 'Antardasha' without a short plain-language "
    "explanation in the same sentence.\n"
    "Translate chart logic into everyday life themes (relationships, timing, emotional patterns).\n"
    "Evidence bullets should read like talking to a friend, not an astrology textbook.\n"
)

_REMEDIES_RULES = (
    "RemediesRules:\n"
    "- Provide 2-3 concrete, practical suggestions in the Remedies section (behavior, communication, "
    "lifestyle, or timing-aware action tied to the chart).\n"
    "- Do not recommend gemstones, mantras, pujas, or yantras as classically grounded facts unless "
    "the claim is directly supported by ClassicalReferences.\n"
    "- If no classical remedy reference is available, keep remedies behavioral and lifestyle-focused only.\n"
)

_SUBTOPIC_SIGNAL_HINTS: list[tuple[re.Pattern[str], list[tuple[str, int]], list[str]]] = [
    (
        re.compile(r"\b(sex|intimacy|physical relationship|bedroom|passion|sexual)\b", re.I),
        [
            ("7th house lord (partnership)", 7),
            ("8th house lord (intimacy/shared resources)", 8),
            ("12th house lord (bed comfort/privacy)", 12),
        ],
        ["Venus", "Mars"],
    ),
    (
        re.compile(r"\b(manglik|mangal dosha|kuja dosha)\b", re.I),
        [],
        ["Mars"],
    ),
]


def _is_promotion_question(user_question: str) -> bool:
    q = (user_question or "").lower()
    return any(term in q for term in ("promotion", "promoted", "salary hike", "raise", "increment"))


def _render_subtopic_signals(features, user_question: str) -> str:
    """Append extra house/planet signals when the question names a specific sub-topic."""
    question = user_question or ""
    if not question.strip():
        return ""

    extra_houses: list[tuple[str, int]] = []
    extra_planets: list[str] = []
    seen_house_nums: set[int] = set()
    seen_planets: set[str] = set()

    for pattern, house_pairs, planets in _SUBTOPIC_SIGNAL_HINTS:
        if not pattern.search(question):
            continue
        for label, house_num in house_pairs:
            if house_num not in seen_house_nums:
                seen_house_nums.add(house_num)
                extra_houses.append((label, house_num))
        for planet in planets:
            if planet not in seen_planets:
                seen_planets.add(planet)
                extra_planets.append(planet)

    if not extra_houses and not extra_planets:
        return ""

    lines = ["SubTopicSignals:"]
    for label, house_num in extra_houses:
        lord = _get_house_lord_for_house(features, house_num)
        lines.append(f"- {label}: {lord or 'Unknown'}")

    dignities = features.get("planetary_dignities", {})
    planets_data = features.get("planets", {})
    for planet in extra_planets:
        data = planets_data.get(planet, {})
        sign = data.get("rashi", "Unknown")
        degrees = data.get("degrees", "?")
        dignity = dignities.get(planet, "[NEUTRAL]")
        lines.append(f"- {planet}: {sign} ({degrees}°), Dignity {dignity}")

    return "\n".join(lines)


def _build_domain_prompt(
    features,
    user_question,
    domain_name,
    summary_label,
    risk_label,
    opportunity_label,
    remedies_label,
    signal_header,
    signal_house_map,
    prior_context=None,
):
    body = (
        f"You are a thoughtful Vedic astrologer focused on {domain_name} guidance.\n"
        "Use only the provided computed data and avoid unsupported claims.\n"
        + _PLAIN_LANGUAGE_RULES
    )
    if cfg.STRUCTURED_OUTPUT_ENABLED:
        body += (
            "Respond with JSON only matching this schema: "
            '{"summary": str, "evidence": [str], "risk": str, "opportunity": str, '
            '"remedies": [str], "confidence": int}.\n'
            "Put chart-based reasoning in evidence strings, but phrase each point in plain English.\n"
            "Put 2-3 practical remedy suggestions in remedies strings.\n\n"
        )
    else:
        body += (
            "Return output in this exact format:\n"
            f"{summary_label}: <3-5 lines in plain English>\n"
            "Evidence:\n"
            "- <plain-language point 1>\n"
            "- <plain-language point 2>\n"
            "- <plain-language point 3>\n"
            f"{risk_label}: <short practical caution in plain English>\n"
            f"{opportunity_label}: <short encouraging note in plain English>\n"
            f"{remedies_label}:\n"
            "- <practical suggestion 1>\n"
            "- <practical suggestion 2>\n"
            "Confidence: <0-100 integer>\n\n"
        )
    body += (
        f"{signal_header}:\n"
        + _render_domain_signals(features, signal_house_map)
    )
    subtopic_block = _render_subtopic_signals(features, user_question)
    if subtopic_block:
        body += "\n\n" + subtopic_block
    body += (
        "\n\nPlanetStrengths:\n"
        + _render_planet_strengths(features)
        + "\n\nFunctionalLords:\n"
        + _render_functional_lords(features)
        + "\n\nCurrentDashas:\n"
        + _render_dasha_section(features)
        + "\n\n"
        + format_dasha_timeline(features["dasha_timeline"])
        + "\n\n"
        + _REMEDIES_RULES
    )
    if question_has_time_horizon(user_question):
        timing_report = build_timing_report(features, question_text=user_question)
        body += "\n\n" + format_timing_context_block(timing_report)
        body += (
            "\n\nTimingAnswerRules:\n"
            "- Because TimingContext is present, the answer MUST include the timing facts, not only general dasha interpretation.\n"
            "- Make the first Evidence bullet start with 'Timing window:' and include WindowStart, WindowEnd, "
            "ActiveAntardasha end date, DaysUntilAntardashaEnd, and whether TransitionsInWindow is none or has changes.\n"
            "- In the summary or evidence, mention the requested window dates and the active Antardasha end date.\n"
            "- Mention the number of days until the active Antardasha ends.\n"
            "- State whether there are dasha or Antardasha transitions inside the requested window.\n"
            "- If NearTerm6Day is present, state whether the coming 6 days show a major dasha change.\n"
        )
        if domain_name == "CAREER" and _is_promotion_question(user_question):
            body += (
                "\nPromotionAnswerRules:\n"
                "- Give a direct promotion verdict in the first sentence: likely, moderate/conditional, delayed, or unlikely.\n"
                "- In Evidence, explicitly connect the verdict to the 10th house/status, 11th house/gains, "
                "6th house/service-competition, and 2nd house/pay or salary themes using the provided CareerSignals.\n"
                "- Do not answer only with generic hard-work advice; tie the practical advice to the timing window.\n"
            )
    body += (
        (f"\n\nPriorContext:\n{prior_context}" if prior_context else "")
        + f"\n\nQuestion: {user_question}"
    )
    return body


def build_career_prompt(features, user_question, prior_context=None):
    return _build_domain_prompt(
        features=features,
        user_question=user_question,
        domain_name="CAREER",
        summary_label="CareerSummary",
        risk_label="CareerRisk",
        opportunity_label="CareerOpportunity",
        remedies_label="CareerRemedies",
        signal_header="CareerSignals",
        signal_house_map=[("10th house lord", 10), ("6th house lord", 6), ("2nd house lord", 2), ("11th house lord", 11)],
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
        remedies_label="HealthRemedies",
        signal_header="HealthSignals",
        signal_house_map=[("1st house lord", 1), ("6th house lord", 6), ("8th house lord", 8), ("12th house lord", 12)],
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
        remedies_label="WealthRemedies",
        signal_header="WealthSignals",
        signal_house_map=[("2nd house lord", 2), ("11th house lord", 11), ("5th house lord", 5), ("9th house lord", 9)],
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
        remedies_label="FamilyRemedies",
        signal_header="FamilySignals",
        signal_house_map=[("4th house lord", 4), ("7th house lord", 7), ("2nd house lord", 2), ("5th house lord", 5)],
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
        remedies_label="OverallRemedies",
        signal_header="GeneralSignals",
        signal_house_map=[("1st house lord", 1), ("4th house lord", 4), ("7th house lord", 7), ("10th house lord", 10)],
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
