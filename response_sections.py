"""Parse domain template answers (CareerSummary / Evidence / … / Confidence) for UI layout."""

from __future__ import annotations

import re

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
