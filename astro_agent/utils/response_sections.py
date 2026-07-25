from __future__ import annotations

import json
import re

from astro_agent.utils.text_utils import format_consumer_text

_SECTION_PATTERNS = {
    "summary": re.compile(
        r"(?:CareerSummary|HealthSummary|WealthSummary|FamilySummary|OverallSummary)\s*:\s*(.*?)(?=\nEvidence:|\Z)",
        re.DOTALL | re.IGNORECASE,
    ),
    "evidence": re.compile(
        r"Evidence\s*:\s*(.*?)(?=\n(?:CareerRisk|HealthRisk|WealthRisk|FamilyRisk|OverallRisk|Confidence)|\Z)",
        re.DOTALL | re.IGNORECASE,
    ),
    "risk": re.compile(
        r"(?:CareerRisk|HealthRisk|WealthRisk|FamilyRisk|OverallRisk)\s*:\s*(.*?)"
        r"(?=\n(?:CareerOpportunity|HealthOpportunity|WealthOpportunity|FamilyOpportunity|OverallOpportunity|Confidence)|\Z)",
        re.DOTALL | re.IGNORECASE,
    ),
    "opportunity": re.compile(
        r"(?:CareerOpportunity|HealthOpportunity|WealthOpportunity|FamilyOpportunity|OverallOpportunity)\s*:\s*(.*?)"
        r"(?=\n(?:CareerRemedies|HealthRemedies|WealthRemedies|FamilyRemedies|OverallRemedies|Remedies|Confidence)|\Z)",
        re.DOTALL | re.IGNORECASE,
    ),
    "remedies": re.compile(
        r"(?:CareerRemedies|HealthRemedies|WealthRemedies|FamilyRemedies|OverallRemedies|Remedies)\s*:\s*(.*?)"
        r"(?=\nConfidence:|\Z)",
        re.DOTALL | re.IGNORECASE,
    ),
    "confidence": re.compile(r"Confidence\s*:\s*(\d+)", re.IGNORECASE),
}


def _parse_bullet_list(text: str) -> list[str]:
    return [
        line.lstrip("- •").strip()
        for line in (text or "").strip().splitlines()
        if line.strip() and line.strip() not in ("-", "•")
    ]


def parse_structured_answer(text: str) -> dict:
    if not (text or "").strip():
        return {"parsed_ok": False}

    try:
        data = json.loads(text)
        if isinstance(data, dict) and "summary" in data:
            conf = data.get("confidence")
            remedies_raw = data.get("remedies")
            if isinstance(remedies_raw, list):
                remedies = [str(r) for r in remedies_raw]
            elif isinstance(remedies_raw, str) and remedies_raw.strip():
                remedies = _parse_bullet_list(remedies_raw)
            else:
                remedies = []
            return {
                "parsed_ok": True,
                "summary": str(data.get("summary", "")),
                "evidence": list(data.get("evidence") or []),
                "risk": str(data.get("risk", "")),
                "opportunity": str(data.get("opportunity", "")),
                "remedies": remedies,
                "confidence_int": int(conf) if conf is not None else None,
                "source": "json",
            }
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    result: dict = {"parsed_ok": False}
    for key, pattern in _SECTION_PATTERNS.items():
        m = pattern.search(text)
        if not m:
            continue
        if key == "confidence":
            result["confidence_int"] = int(m.group(1))
        elif key in ("evidence", "remedies"):
            result[key] = _parse_bullet_list(m.group(1))
        else:
            result[key] = m.group(1).strip()

    if result.get("summary"):
        result["parsed_ok"] = True
        result.setdefault("source", "template")

    return result


def format_chat_answer_fallback(parsed: dict, raw_text: str) -> str:
    """Deterministic stitcher when humanize_answer fails; no section labels or confidence score."""
    if not parsed.get("parsed_ok"):
        return format_consumer_text(raw_text or "")

    parts: list[str] = []

    summary = parsed.get("summary", "")
    if summary:
        parts.append(format_consumer_text(summary))

    evidence = parsed.get("evidence") or []
    if evidence:
        parts.append("\n**Key points**")
        for bullet in evidence:
            parts.append(f"- {format_consumer_text(bullet)}")

    risk = parsed.get("risk", "")
    if risk:
        parts.append(f"\n**Cautions** {format_consumer_text(risk)}")

    opportunity = parsed.get("opportunity", "")
    if opportunity:
        parts.append(f"\n**Upside** {format_consumer_text(opportunity)}")

    remedies = parsed.get("remedies") or []
    if remedies:
        parts.append("\n**Practical steps**")
        for bullet in remedies:
            parts.append(f"- {format_consumer_text(bullet)}")

    return "\n".join(parts)


# Backward-compatible alias for callers not yet updated.
format_chat_answer_markdown = format_chat_answer_fallback
