"""Timing windows, horizon parsing, and dasha transition reports."""

from __future__ import annotations

import calendar
import datetime
import re
from typing import Any

from astro_agent.chart.dashas import calculate_antardashas, get_current_and_next_antardasha

_WORD_NUMBERS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}

_HORIZON_PATTERNS = [
    re.compile(
        r"\b(?:next|coming|in the next|over the next)\s+"
        r"(?:(\d+)|(" + "|".join(_WORD_NUMBERS.keys()) + r"))\s+"
        r"(days?|weeks?|months?|years?)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bhalf\s+year\b", re.IGNORECASE),
    re.compile(r"\bsix\s+months?\b", re.IGNORECASE),
    re.compile(r"\bthis\s+year\b", re.IGNORECASE),
    re.compile(r"\bnext\s+year\b", re.IGNORECASE),
    re.compile(
        r"\b(?:next|coming)\s+week\b|\b(?:in|over)\s+the\s+coming\s+week\b",
        re.IGNORECASE,
    ),
]

_OPEN_TIMING_RE = re.compile(
    r"\bwhen\s+will\b|\bwhen\s+can\b|\bsoon\b|\bcoming\s+up\b|"
    r"\bmajor\s+life\s+changes?\b|\bfavo(?:u)?rable\s+period\b|\bright\s+now\b",
    re.IGNORECASE,
)


def _parse_iso_date(value: str | datetime.date | None) -> datetime.date | None:
    if value is None:
        return None
    if isinstance(value, datetime.date):
        return value
    text = str(value).strip()
    if not text:
        return None
    return datetime.date.fromisoformat(text)


def _add_months(d: datetime.date, months: int) -> datetime.date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return datetime.date(year, month, day)


def _get_current_and_next_dasha(timeline: list, on_date: datetime.date) -> tuple[dict | None, dict | None]:
    current = None
    upcoming = None
    for idx, d in enumerate(timeline):
        start = datetime.date.fromisoformat(d["start"])
        end = datetime.date.fromisoformat(d["end"])
        if start <= on_date <= end:
            current = d
            if idx + 1 < len(timeline):
                upcoming = timeline[idx + 1]
            break
    if current is None and timeline:
        current = timeline[0]
        upcoming = timeline[1] if len(timeline) > 1 else None
    return current, upcoming


def question_has_time_horizon(text: str) -> bool:
    return parse_horizon(text) is not None


def parse_horizon(text: str, as_of_date: datetime.date | None = None) -> tuple[datetime.date, datetime.date] | None:
    """Parse a natural-language horizon from question text."""
    anchor = as_of_date or datetime.date.today()
    lowered = (text or "").lower()

    if re.search(r"\bhalf\s+year\b", lowered) or re.search(r"\bsix\s+months?\b", lowered):
        return anchor, _add_months(anchor, 6)

    if re.search(r"\bthis\s+year\b", lowered):
        return anchor, datetime.date(anchor.year, 12, 31)

    if re.search(r"\bnext\s+year\b", lowered):
        start = datetime.date(anchor.year + 1, 1, 1)
        return start, datetime.date(anchor.year + 1, 12, 31)

    if re.search(r"\b(?:next|coming)\s+week\b|\b(?:in|over)\s+the\s+coming\s+week\b", lowered):
        return anchor, anchor + datetime.timedelta(days=7)

    match = _HORIZON_PATTERNS[0].search(text or "")
    if match:
        raw_num = match.group(1) or match.group(2)
        unit = match.group(3).lower()
        count = int(raw_num) if raw_num.isdigit() else _WORD_NUMBERS.get(raw_num.lower(), 0)
        if count <= 0:
            return None
        if unit.startswith("day"):
            end = anchor + datetime.timedelta(days=count)
        elif unit.startswith("week"):
            end = anchor + datetime.timedelta(days=7 * count)
        elif unit.startswith("month"):
            end = _add_months(anchor, count)
        elif unit.startswith("year"):
            end = _add_months(anchor, 12 * count)
        else:
            return None
        return anchor, end

    if _OPEN_TIMING_RE.search(text or ""):
        return anchor, _add_months(anchor, 12)

    return None


def resolve_window(
    *,
    window_text: str | None = None,
    as_of_date: datetime.date | None = None,
    start_date: str | datetime.date | None = None,
    end_date: str | datetime.date | None = None,
    question_text: str | None = None,
) -> tuple[datetime.date, datetime.date] | None:
    anchor = as_of_date or datetime.date.today()
    explicit_start = _parse_iso_date(start_date)
    explicit_end = _parse_iso_date(end_date)
    if explicit_start and explicit_end:
        return explicit_start, explicit_end

    for source in (window_text, question_text):
        if source:
            parsed = parse_horizon(source, anchor)
            if parsed:
                return parsed
    return None


def _period_dict(period: dict | None) -> dict[str, Any] | None:
    if not period:
        return None
    return {
        "lord": period.get("dasha"),
        "start": period.get("start"),
        "end": period.get("end"),
        "kind": period.get("kind", "mahadasha" if "is_birth_dasha" in period else "antardasha"),
    }


def _days_until(end_iso: str | None, on_date: datetime.date) -> int | None:
    if not end_iso:
        return None
    end = datetime.date.fromisoformat(end_iso)
    return max(0, (end - on_date).days)


def _collect_antardasha_segments_for_md(md: dict) -> list[dict]:
    m_start = datetime.date.fromisoformat(md["start"])
    m_end = datetime.date.fromisoformat(md["end"])
    return calculate_antardashas(md["dasha"], m_start, m_end)


def _transitions_in_window(
    timeline: list,
    window_start: datetime.date,
    window_end: datetime.date,
) -> list[dict[str, Any]]:
    transitions: list[dict[str, Any]] = []

    for idx, md in enumerate(timeline):
        md_start = datetime.date.fromisoformat(md["start"])
        md_end = datetime.date.fromisoformat(md["end"])
        if md_end < window_start or md_start > window_end:
            continue

        if idx > 0 and window_start <= md_start <= window_end:
            transitions.append(
                {
                    "type": "mahadasha",
                    "lord": md["dasha"],
                    "date": md["start"],
                    "end": md["end"],
                }
            )

        antars = _collect_antardasha_segments_for_md(md)
        for ad_idx, ad in enumerate(antars):
            ad_start = datetime.date.fromisoformat(ad["start"])
            ad_end = datetime.date.fromisoformat(ad["end"])
            if ad_end < window_start or ad_start > window_end:
                continue
            if ad_idx > 0 and window_start <= ad_start <= window_end:
                transitions.append(
                    {
                        "type": "antardasha",
                        "lord": ad["dasha"],
                        "date": ad["start"],
                        "end": ad["end"],
                        "mahadasha": md["dasha"],
                    }
                )

    transitions.sort(key=lambda item: item["date"])
    return transitions


def _build_near_term_checkpoint(
    timeline: list,
    as_of_date: datetime.date,
) -> dict[str, Any]:
    checkpoint_end = as_of_date + datetime.timedelta(days=6)
    transitions = _transitions_in_window(timeline, as_of_date, checkpoint_end)
    active_md, _ = _get_current_and_next_dasha(timeline, as_of_date)
    active_ad = None
    if active_md:
        antars = _collect_antardasha_segments_for_md(active_md)
        active_ad, _ = get_current_and_next_antardasha(antars, as_of_date)
    return {
        "window_start": as_of_date.isoformat(),
        "window_end": checkpoint_end.isoformat(),
        "horizon_days": 6,
        "transitions": transitions,
        "active_mahadasha": _period_dict(active_md),
        "active_antardasha": _period_dict(active_ad),
    }


def build_timing_report(
    features: dict,
    *,
    window_text: str | None = None,
    as_of_date: datetime.date | str | None = None,
    start_date: str | datetime.date | None = None,
    end_date: str | datetime.date | None = None,
    question_text: str | None = None,
) -> dict[str, Any]:
    """Single source of truth for timing windows and dasha transitions."""
    on_date = _parse_iso_date(as_of_date) or datetime.date.today()
    timeline = features.get("dasha_timeline") or []

    window = resolve_window(
        window_text=window_text,
        as_of_date=on_date,
        start_date=start_date,
        end_date=end_date,
        question_text=question_text,
    )
    if not window:
        window_start = on_date
        window_end = on_date
    else:
        window_start, window_end = window

    active_md, _ = _get_current_and_next_dasha(timeline, on_date)
    active_ad = None
    if active_md:
        antars = _collect_antardasha_segments_for_md(active_md)
        active_ad, _ = get_current_and_next_antardasha(antars, on_date)

    horizon_days = max(0, (window_end - window_start).days)
    transitions = _transitions_in_window(timeline, window_start, window_end)

    report: dict[str, Any] = {
        "as_of_date": on_date.isoformat(),
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "horizon_days": horizon_days,
        "active_mahadasha": _period_dict(active_md),
        "active_antardasha": _period_dict(active_ad),
        "days_until_antardasha_end": _days_until(active_ad.get("end") if active_ad else None, on_date),
        "days_until_mahadasha_end": _days_until(active_md.get("end") if active_md else None, on_date),
        "transitions": transitions,
        "near_term_6_day": None,
    }

    if horizon_days > 6:
        report["near_term_6_day"] = _build_near_term_checkpoint(timeline, on_date)

    return report


def format_timing_context_block(report: dict[str, Any]) -> str:
    """Compact prompt block for linear/RAG injection."""
    lines = [
        "TimingContext:",
        "- TimingInstruction: You MUST use these timing facts in the answer. State the asked window, the active "
        "Antardasha end date, days until it ends, whether transitions occur in the window, and the 6-day checkpoint "
        "when present. If TransitionsInWindow is none, explicitly say there is no major dasha change in the asked window.",
        f"- TodayDate: {report.get('as_of_date')}",
        f"- WindowStart: {report.get('window_start')}",
        f"- WindowEnd: {report.get('window_end')}",
        f"- HorizonDays: {report.get('horizon_days')}",
    ]

    active_md = report.get("active_mahadasha") or {}
    active_ad = report.get("active_antardasha") or {}
    if active_md:
        lines.append(f"- ActiveMahadasha: {active_md.get('lord')} ({active_md.get('start')} to {active_md.get('end')})")
    if active_ad:
        lines.append(
            f"- ActiveAntardasha: {active_ad.get('lord')} ({active_ad.get('start')} to {active_ad.get('end')})"
        )

    if report.get("days_until_antardasha_end") is not None:
        lines.append(f"- DaysUntilAntardashaEnd: {report['days_until_antardasha_end']}")
    if report.get("days_until_mahadasha_end") is not None:
        lines.append(f"- DaysUntilMahadashaEnd: {report['days_until_mahadasha_end']}")

    transitions = report.get("transitions") or []
    if transitions:
        lines.append("- TransitionsInWindow:")
        for tr in transitions:
            md_note = f" under {tr['mahadasha']} MD" if tr.get("mahadasha") else ""
            lines.append(f"  - {tr['type']} change to {tr['lord']} on {tr['date']}{md_note} (until {tr['end']})")
    else:
        lines.append("- TransitionsInWindow: none")

    near = report.get("near_term_6_day")
    if near:
        lines.append("- NearTerm6Day:")
        lines.append(f"  - WindowEnd: {near.get('window_end')}")
        near_transitions = near.get("transitions") or []
        if near_transitions:
            for tr in near_transitions:
                lines.append(f"  - {tr['type']} change to {tr['lord']} on {tr['date']}")
        else:
            lines.append("  - No major dasha changes in the next 6 days")

    return "\n".join(lines)
