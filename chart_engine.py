"""Chart computation (ephemeris, dashas, bhava)."""
import swisseph as swe
from datetime import date, datetime
from mapper import get_vedic_details
from cities import resolve_city_coordinates
from utils import convert_ist_to_utc
from lords import RASHIS, get_house_lords
from yogas import apply_tags_to_chart
from dashas import (
    calculate_antardashas,
    calculate_dashas,
    get_current_and_next_antardasha,
)

def _setup_julian_day(year, month, day, hour_utc):
    """Prepare sidereal mode and Julian day."""
    swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
    return swe.julday(year, month, day, hour_utc)


def _bhava_house_for_longitude(longitude, cusps):
    """Return Placidus bhava (1–12) for sidereal longitude.

    ``cusps`` is the 12-element array from ``swe.houses_ex`` (index 0 = house 1 cusp).
    """
    lon = float(longitude) % 360.0
    n = len(cusps)
    if n < 12:
        return None
    for idx in range(12):
        c_start = float(cusps[idx]) % 360.0
        c_end = float(cusps[(idx + 1) % 12]) % 360.0
        house = idx + 1
        if c_start <= c_end:
            if c_start <= lon < c_end:
                return house
        elif lon >= c_start or lon < c_end:
            return house
    return 12


def _compute_chart_core(year, month, day, hour_utc, city_name="bengaluru"):
    """Compute lagna and planetary placements in a structured format."""
    jd = _setup_julian_day(year, month, day, hour_utc)
    geo = resolve_city_coordinates(city_name)

    hres = swe.houses_ex(jd, geo["lat"], geo["lon"], b"P", swe.FLG_SIDEREAL)
    cusps = hres[0]
    ascendant_long = hres[1][0]
    lagna_details = get_vedic_details(ascendant_long)

    planets = {
        "Sun": swe.SUN, "Moon": swe.MOON, "Mars": swe.MARS, "Mercury": swe.MERCURY,
        "Jupiter": swe.JUPITER, "Venus": swe.VENUS, "Saturn": swe.SATURN, "Rahu": swe.MEAN_NODE
    }

    placements = {}
    rahu_long = 0
    for name, id in planets.items():
        res, _ = swe.calc_ut(jd, id, swe.FLG_SIDEREAL)
        long = res[0]
        if name == "Rahu":
            rahu_long = long
        details = get_vedic_details(long)
        placements[name] = {
            "longitude": round(long, 4),
            "rashi": details["rashi"],
            "degrees": details["degrees"],
            "nakshatra": details["nakshatra"],
        }

    ketu_details = get_vedic_details((rahu_long + 180) % 360)
    placements["Ketu"] = {
        "longitude": round((rahu_long + 180) % 360, 4),
        "rashi": ketu_details["rashi"],
        "degrees": ketu_details["degrees"],
        "nakshatra": ketu_details["nakshatra"],
    }

    return {
        "lagna": {
            "longitude": round(ascendant_long, 4),
            "rashi": lagna_details["rashi"],
            "degrees": lagna_details["degrees"],
            "nakshatra": lagna_details["nakshatra"],
        },
        "planets": placements,
        "coordinates": geo,
        "julian_day": jd,
        "house_cusps": [round(float(c), 4) for c in cusps],
    }


def _get_current_and_next_dasha(timeline, on_date):
    """Return the active and next Mahadasha for a date."""
    current = None
    upcoming = None
    for idx, d in enumerate(timeline):
        start = datetime.strptime(d["start"], "%Y-%m-%d").date()
        end = datetime.strptime(d["end"], "%Y-%m-%d").date()
        if start <= on_date <= end:
            current = d
            if idx + 1 < len(timeline):
                upcoming = timeline[idx + 1]
            break
    if current is None and timeline:
        current = timeline[0]
        upcoming = timeline[1] if len(timeline) > 1 else None
    return current, upcoming


def build_chart_features(year, month, day, hour, minute, city_name="bengaluru"):
    """Build unified chart features using all local rule modules."""
    time_data = convert_ist_to_utc(year, month, day, hour, minute)
    core = _compute_chart_core(
        time_data["year"], time_data["month"], time_data["day"], time_data["hour_utc"], city_name
    )

    lagna_rashi = core["lagna"]["rashi"]
    house_lords = get_house_lords(lagna_rashi)
    cusps = core.get("house_cusps") or [None] * 13

    sign_houses = {}
    bhava_positions = {}
    for planet, data in core["planets"].items():
        sign = data.get("rashi")
        sign_houses[planet] = _house_number_from_lagna_and_sign(lagna_rashi, sign)
        blon = data.get("longitude")
        if blon is not None and cusps and len(cusps) >= 12:
            bhava_positions[planet] = _bhava_house_for_longitude(blon, cusps)

    planet_rashis = {planet: data["rashi"] for planet, data in core["planets"].items()}
    dignity_tags = apply_tags_to_chart(planet_rashis)

    moon_longitude = core["planets"]["Moon"]["longitude"]
    timeline = calculate_dashas(moon_longitude, year, month, day)
    current_dasha, next_dasha = _get_current_and_next_dasha(timeline, date.today())

    active_antardasha = None
    next_antardasha = None
    antardasha_timeline_current_md = []
    if current_dasha:
        m_start = datetime.strptime(current_dasha["start"], "%Y-%m-%d").date()
        m_end = datetime.strptime(current_dasha["end"], "%Y-%m-%d").date()
        antardasha_timeline_current_md = calculate_antardashas(
            current_dasha["dasha"], m_start, m_end
        )
        active_antardasha, next_antardasha = get_current_and_next_antardasha(
            antardasha_timeline_current_md, date.today()
        )

    return {
        "birth_input_ist": {
            "year": year,
            "month": month,
            "day": day,
            "hour": hour,
            "minute": minute,
            "city_name": city_name,
        },
        "birth_time_utc": time_data,
        "lagna": core["lagna"],
        "planets": core["planets"],
        "house_lordships": house_lords,
        "planetary_dignities": dignity_tags,
        "dasha_timeline": timeline,
        "active_dasha": current_dasha,
        "next_dasha": next_dasha,
        "active_antardasha": active_antardasha,
        "next_antardasha": next_antardasha,
        "antardasha_timeline_current_md": antardasha_timeline_current_md,
        "coordinates": core["coordinates"],
        "sign_houses": sign_houses,
        "bhava_positions": bhava_positions,
        "house_cusps": core.get("house_cusps"),
    }


def generate_full_chart(year, month, day, hour, minute, city_name="bengaluru"):
    """Backward-compatible text formatter over structured chart features."""
    features = build_chart_features(year, month, day, hour, minute, city_name)
    lines = [
        f"Lagna (Ascendant): {features['lagna']['rashi']} at {features['lagna']['degrees']}°",
    ]
    for name, details in features["planets"].items():
        lines.append(f"{name}: {details['rashi']} ({details['degrees']}°) - {details['nakshatra']}")
    return "\n".join(lines)


def generate_chart_facts(year, month, day, hour_utc):
    """Legacy baseline facts from ephemeris (used for eval comparison)."""
    core = _compute_chart_core(year, month, day, hour_utc)
    lines = []
    for name, details in core["planets"].items():
        lines.append(
            f"{name}: {details['rashi']} ({details['degrees']}°) - Nakshatra: {details['nakshatra']}"
        )
    return "\n".join(lines)


def _get_house_lord_for_house(features, house_number):
    return next(
        (planet for planet, houses in features["house_lordships"].items() if house_number in houses),
        "Unknown",
    )


def _render_planet_strengths(features):
    lines = []
    for planet, data in features["planets"].items():
        dignity = features["planetary_dignities"].get(planet, "[NEUTRAL]")
        lines.append(
            f"- {planet}: {data['rashi']} ({data['degrees']}°), Nakshatra {data['nakshatra']}, Dignity {dignity}"
        )
    return "\n".join(lines)


def _render_functional_lords(features):
    lines = []
    for planet, houses in features["house_lordships"].items():
        if houses:
            lines.append(f"- {planet}: houses {houses}")
    return "\n".join(lines)


def _render_dasha_section(features):
    active_dasha = features["active_dasha"] or {}
    next_dasha = features["next_dasha"] or {}
    active_ant = features.get("active_antardasha") or {}
    next_ant = features.get("next_antardasha") or {}
    lines = [
        f"- Active Mahadasha: {active_dasha.get('dasha', 'Unknown')} ({active_dasha.get('start', '?')} to {active_dasha.get('end', '?')})",
        f"- Active Antardasha: {active_ant.get('dasha', 'Unknown')} ({active_ant.get('start', '?')} to {active_ant.get('end', '?')})",
        f"- Next Mahadasha: {next_dasha.get('dasha', 'Unknown')} ({next_dasha.get('start', '?')} to {next_dasha.get('end', '?')})",
        f"- Next Antardasha: {next_ant.get('dasha', 'Unknown')} ({next_ant.get('start', '?')} to {next_ant.get('end', '?')})",
    ]
    return "\n".join(lines)


def _render_domain_signals(features, label_to_house):
    lines = []
    for label, house_num in label_to_house:
        lines.append(f"- {label}: {_get_house_lord_for_house(features, house_num)}")
    return "\n".join(lines)


def _house_number_from_lagna_and_sign(lagna_rashi, planet_rashi):
    try:
        lagna_idx = RASHIS.index(lagna_rashi)
        planet_idx = RASHIS.index(planet_rashi)
    except ValueError:
        return None
    return ((planet_idx - lagna_idx) % 12) + 1
