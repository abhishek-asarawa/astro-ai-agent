# dashas.py
import datetime

# Dasha sequence and their total durations in years (full cycle = 120 years)
DASHA_SEQUENCE = [
    ("Ketu", 7),
    ("Venus", 20),
    ("Sun", 6),
    ("Moon", 10),
    ("Mars", 7),
    ("Rahu", 18),
    ("Jupiter", 16),
    ("Saturn", 19),
    ("Mercury", 17),
]

_LORD_TO_INDEX = {name: i for i, (name, _) in enumerate(DASHA_SEQUENCE)}


def calculate_dashas(moon_longitude: float, birth_year: int, birth_month: int, birth_day: int) -> list:
    """
    Calculates the Vimshottari Mahadasha timeline for a 120-year cycle.
    Returns a list of dictionaries with start and end dates.
    """
    nak_size = 360 / 27  # 13.3333 degrees per Nakshatra

    # 1. Determine which Nakshatra the moon is in
    nak_index = int(moon_longitude / nak_size)

    # 2. Determine the starting Dasha Lord (index 0-8 in sequence)
    dasha_start_index = nak_index % 9

    # 3. Calculate fraction of Nakshatra remaining
    elapsed_in_nak = moon_longitude % nak_size
    fraction_remaining = 1.0 - (elapsed_in_nak / nak_size)

    # Initialize the birth date
    current_date = datetime.date(birth_year, birth_month, birth_day)
    timeline = []

    # First Dasha is partial
    first_lord, first_total_years = DASHA_SEQUENCE[dasha_start_index]
    first_duration_years = first_total_years * fraction_remaining
    first_duration_days = first_duration_years * 365.25

    end_date = current_date + datetime.timedelta(days=first_duration_days)

    timeline.append(
        {
            "dasha": first_lord,
            "start": current_date.strftime("%Y-%m-%d"),
            "end": end_date.strftime("%Y-%m-%d"),
            "is_birth_dasha": True,
        }
    )

    current_date = end_date

    # Calculate the remaining Dashas to complete a full 120-year cycle
    for offset in range(1, 9):
        idx = (dasha_start_index + offset) % 9
        lord, total_years = DASHA_SEQUENCE[idx]

        duration_days = total_years * 365.25
        end_date = current_date + datetime.timedelta(days=duration_days)

        timeline.append(
            {
                "dasha": lord,
                "start": current_date.strftime("%Y-%m-%d"),
                "end": end_date.strftime("%Y-%m-%d"),
                "is_birth_dasha": False,
            }
        )

        current_date = end_date

    return timeline


def calculate_antardashas(
    mahadasha_lord: str,
    maha_start: datetime.date,
    maha_end: datetime.date,
) -> list:
    """
    Vimshottari Antardashas within one Mahadasha window.

    Order starts with the mahadasha lord, then follows DASHA_SEQUENCE.
    Each antar length = (lord_years / 120) * mahadasha_span, matching the
    same 365.25-day year convention as calculate_dashas for the MD span.
    """
    if mahadasha_lord not in _LORD_TO_INDEX or maha_end <= maha_start:
        return []

    start_idx = _LORD_TO_INDEX[mahadasha_lord]
    md_total_days = (maha_end - maha_start).total_seconds() / 86400.0
    if md_total_days <= 0:
        return []

    timeline = []
    current = maha_start
    for offset in range(9):
        idx = (start_idx + offset) % 9
        lord, total_years = DASHA_SEQUENCE[idx]
        if offset < 8:
            duration_days = (total_years / 120.0) * md_total_days
            end = current + datetime.timedelta(days=duration_days)
        else:
            end = maha_end
        timeline.append(
            {
                "dasha": lord,
                "start": current.strftime("%Y-%m-%d"),
                "end": end.strftime("%Y-%m-%d"),
                "kind": "antardasha",
            }
        )
        current = end

    return timeline


def get_current_and_next_antardasha(antar_timeline: list, on_date: datetime.date) -> tuple:
    """Return the active and next Antardasha dicts for on_date (same contract as MD helpers)."""
    current = None
    upcoming = None
    if not antar_timeline:
        return current, upcoming
    for idx, d in enumerate(antar_timeline):
        start = datetime.date.fromisoformat(d["start"])
        end = datetime.date.fromisoformat(d["end"])
        if start <= on_date <= end:
            current = d
            if idx + 1 < len(antar_timeline):
                upcoming = antar_timeline[idx + 1]
            break
    if current is None:
        current = antar_timeline[0]
        upcoming = antar_timeline[1] if len(antar_timeline) > 1 else None
    return current, upcoming


def format_dasha_timeline(timeline: list) -> str:
    """Formats the timeline list into a readable string block for the AI prompt."""
    output = ["--- VIMSHOTTARI DASHA TIMELINE ---"]
    for d in timeline:
        birth_tag = "(Birth Dasha)" if d["is_birth_dasha"] else ""
        output.append(f"{d['dasha']} Mahadasha: {d['start']} to {d['end']} {birth_tag}")
    return "\n".join(output)
