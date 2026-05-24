"""Parse domain template answers (CareerSummary / Evidence / … / Confidence) for UI layout."""

from __future__ import annotations

import json
import re

from text_utils import format_consumer_text

_SUMMARY = (
    "CareerSummary",
    "HealthSummary",
    "WealthSummary",
    "FamilySummary",
    "OverallSummary",
)
_RISK = (
    "CareerRisk",
    "HealthRisk",
    "WealthRisk",
    "FamilyRisk",
    "OverallRisk",
)
_OPPORTUNITY = (
    "CareerOpportunity",
    "HealthOpportunity",
    "WealthOpportunity",
    "FamilyOpportunity",
    "OverallOpportunity",
)


def parse_structured_answer(text: str | None) -> dict:
    """Extract summary, evidence, risk, opportunity, confidence from model output.

    Returns keys: summary, evidence, risk, opportunity, confidence (str),
    confidence_int (int|None), parsed_ok (bool).
    """
    out: dict = {
        "summary": None,
        "evidence": None,
        "risk": None,
        "opportunity": None,
        "confidence": None,
        "confidence_int": None,
        "parsed_ok": False,
    }
    if not text or not str(text).strip():
        return out
    t = str(text).strip()

    # JSON structured output (Phase 5b)
    if t.startswith("{") or t.startswith("```"):
        raw = t
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
            raw = re.sub(r"\s*```\s*$", "", raw)
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                out["summary"] = (data.get("summary") or "").strip() or None
                ev = data.get("evidence")
                if isinstance(ev, list):
                    out["evidence"] = "\n".join(f"- {x}" for x in ev if str(x).strip())
                elif isinstance(ev, str):
                    out["evidence"] = ev.strip() or None
                out["risk"] = (data.get("risk") or "").strip() or None
                out["opportunity"] = (data.get("opportunity") or "").strip() or None
                conf = data.get("confidence")
                if conf is not None:
                    out["confidence"] = str(conf)
                    try:
                        out["confidence_int"] = int(conf)
                    except (TypeError, ValueError):
                        out["confidence_int"] = None
                out["parsed_ok"] = bool(
                    out["summary"] or out["evidence"] or out["risk"] or out["opportunity"]
                )
                return out
        except json.JSONDecodeError:
            pass

    summ_pat = "|".join(re.escape(s) for s in _SUMMARY)
    summ_re = re.compile(
        rf"(?is)^(?P<label>{summ_pat})\s*:\s*(?P<body>.*?)(?=^\s*Evidence\s*:|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m2 = summ_re.search(t)
    if m2:
        out["summary"] = m2.group("body").strip()

    risk_pat = "|".join(re.escape(s) for s in _RISK)
    opp_pat = "|".join(re.escape(s) for s in _OPPORTUNITY)

    ev_re = re.compile(
        rf"(?is)^\s*Evidence\s*:\s*(?P<body>.*?)(?=^\s*(?:{risk_pat})\s*:|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    me = ev_re.search(t)
    if me:
        out["evidence"] = me.group("body").strip()

    risk_re = re.compile(
        rf"(?is)^\s*(?P<label>{risk_pat})\s*:\s*(?P<body>.*?)(?=^\s*(?:{opp_pat})\s*:|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    mr = risk_re.search(t)
    if mr:
        out["risk"] = mr.group("body").strip()

    opp_re = re.compile(
        rf"(?is)^\s*(?P<label>{opp_pat})\s*:\s*(?P<body>.*?)(?=^\s*Confidence\s*:|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    mo = opp_re.search(t)
    if mo:
        out["opportunity"] = mo.group("body").strip()

    conf_re = re.compile(r"(?im)^\s*Confidence\s*:\s*(\d{1,3})\b")
    mc = conf_re.search(t)
    if mc:
        out["confidence"] = mc.group(1).strip()
        try:
            out["confidence_int"] = int(mc.group(1))
        except ValueError:
            out["confidence_int"] = None

    out["parsed_ok"] = bool(
        out["summary"] or out["evidence"] or out["risk"] or out["opportunity"] or out["confidence"]
    )
    return out


def format_chat_answer_markdown(parsed: dict, raw_fallback: str) -> str:
    """Build a single chat-friendly markdown answer from structured fields."""
    if not parsed.get("parsed_ok"):
        return format_consumer_text(raw_fallback)

    parts: list[str] = []
    summary = format_consumer_text(parsed.get("summary") or "")
    if summary:
        parts.append(f"**In short**\n\n{summary}")

    evidence = format_consumer_text(parsed.get("evidence") or "")
    if evidence:
        parts.append(f"**What stands out**\n\n{evidence}")

    risk = format_consumer_text(parsed.get("risk") or "")
    if risk:
        parts.append(f"**What to be careful about**\n\n{risk}")

    opportunity = format_consumer_text(parsed.get("opportunity") or "")
    if opportunity:
        parts.append(f"**What can help**\n\n{opportunity}")

    ci = parsed.get("confidence_int")
    if ci is not None and 0 <= ci <= 100:
        parts.append(
            "**How confident this reading is**\n\n"
            f"About **{ci}** out of 100 — this reflects how clear the chart signals are, "
            "not a guarantee about real life."
        )
    elif parsed.get("confidence"):
        parts.append(
            "**How confident this reading is**\n\n"
            + format_consumer_text(str(parsed["confidence"]))
        )

    if parts:
        return "\n\n".join(parts)
    return format_consumer_text(raw_fallback)
