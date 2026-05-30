from __future__ import annotations

import json
import re

from astro_agent.utils.text_utils import format_consumer_text

_SECTION_PATTERNS = {
    "summary": re.compile(
        r"(?:CareerSummary|HealthSummary|WealthSummary|FamilySummary|OverallSummary)\s*:\s*(.*?)(?=\nEvidence:|\Z)",
        re.DOTALL | re.IGNORECASE,
    ),
    "evidence": re.compile(r"Evidence\s*:\s*(.*?)(?=\n(?:CareerRisk|HealthRisk|WealthRisk|FamilyRisk|OverallRisk|Confidence)|\Z)", re.DOTALL | re.IGNORECASE),
    "risk": re.compile(r"(?:CareerRisk|HealthRisk|WealthRisk|FamilyRisk|OverallRisk)\s*:\s*(.*?)(?=\n(?:CareerOpportunity|HealthOpportunity|WealthOpportunity|FamilyOpportunity|OverallOpportunity|Confidence)|\Z)", re.DOTALL | re.IGNORECASE),
    "opportunity": re.compile(r"(?:CareerOpportunity|HealthOpportunity|WealthOpportunity|FamilyOpportunity|OverallOpportunity)\s*:\s*(.*?)(?=\nConfidence:|\Z)", re.DOTALL | re.IGNORECASE),
    "confidence": re.compile(r"Confidence\s*:\s*(\d+)", re.IGNORECASE),
}


def parse_structured_answer(text: str) -> dict:
    if not (text or "").strip():
        return {"parsed_ok": False}

    try:
        data = json.loads(text)
        if isinstance(data, dict) and "summary" in data:
            conf = data.get("confidence")
            return {
                "parsed_ok": True,
                "summary": str(data.get("summary", "")),
                "evidence": list(data.get("evidence") or []),
                "risk": str(data.get("risk", "")),
                "opportunity": str(data.get("opportunity", "")),
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
        elif key == "evidence":
            bullets = [
                line.lstrip("- •").strip()
                for line in m.group(1).strip().splitlines()
                if line.strip() and line.strip() not in ("-", "•")
            ]
            result["evidence"] = bullets
        else:
            result[key] = m.group(1).strip()

    if result.get("summary"):
        result["parsed_ok"] = True
        result.setdefault("source", "template")

    return result


def format_chat_answer_markdown(parsed: dict, raw_text: str) -> str:
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

    conf = parsed.get("confidence_int")
    if conf is not None:
        label = "Low" if conf < 40 else ("Moderate" if conf < 70 else "Good")
        parts.append(f"\n**Confidence** {label} ({conf}/100)")

    return "\n".join(parts)
