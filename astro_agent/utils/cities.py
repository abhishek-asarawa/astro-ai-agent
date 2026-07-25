"""City name → coordinates resolution (static table + geopy Nominatim fallback)."""

from __future__ import annotations

import re
from functools import lru_cache

# Common Indian cities (fast path, no network)
CITY_COORDINATES = {
    "bengaluru": {"lat": 12.9716, "lon": 77.5946},
    "mumbai": {"lat": 19.0760, "lon": 72.8777},
    "delhi": {"lat": 28.6139, "lon": 77.2090},
    "chennai": {"lat": 13.0827, "lon": 80.2707},
    "hyderabad": {"lat": 17.3850, "lon": 78.4867},
    "kolkata": {"lat": 22.5726, "lon": 88.3639},
    "pune": {"lat": 18.5204, "lon": 73.8567},
    "ahmedabad": {"lat": 23.0225, "lon": 72.5714},
    "jaipur": {"lat": 26.9124, "lon": 75.7873},
    "lucknow": {"lat": 26.8467, "lon": 80.9462},
    "chandigarh": {"lat": 30.7333, "lon": 76.7794},
    "kochi": {"lat": 9.9312, "lon": 76.2673},
    "indore": {"lat": 22.7196, "lon": 75.8577},
    "bhopal": {"lat": 23.2599, "lon": 77.4126},
    "nagpur": {"lat": 21.1458, "lon": 79.0882},
    "surat": {"lat": 21.1702, "lon": 72.8311},
    "visakhapatnam": {"lat": 17.6868, "lon": 83.2185},
    "patna": {"lat": 25.5941, "lon": 85.1376},
    "guwahati": {"lat": 26.1445, "lon": 91.7362},
    "thiruvananthapuram": {"lat": 8.5241, "lon": 76.9366},
}

_CITY_ALIASES = {
    "bangalore": "bengaluru",
    "bombay": "mumbai",
    "new delhi": "delhi",
    "madras": "chennai",
    "calcutta": "kolkata",
    "trivandrum": "thiruvananthapuram",
}


class CityResolutionError(ValueError):
    """Raised when a birth city cannot be resolved to coordinates."""


def _normalize_city_key(city_name: str) -> str:
    key = re.sub(r"\s+", " ", (city_name or "").strip().lower())
    return _CITY_ALIASES.get(key, key)


@lru_cache(maxsize=256)
def resolve_city_coordinates(city_name: str) -> dict:
    """Resolve city to ``lat``, ``lon``, ``source``, and ``label``.

    Raises ``CityResolutionError`` on failure (no silent fallback).
    """
    if not (city_name or "").strip():
        raise CityResolutionError("Birth city is required.")

    key = _normalize_city_key(city_name)
    static = CITY_COORDINATES.get(key)
    if static:
        return {
            "lat": static["lat"],
            "lon": static["lon"],
            "source": "static",
            "label": key,
        }

    try:
        from geopy.geocoders import Nominatim
    except ImportError as exc:
        raise CityResolutionError(f"City '{city_name}' is not in the static list and geopy is not installed.") from exc

    geocoder = Nominatim(user_agent="astro-ai-agent/1.0", timeout=5)
    query = city_name.strip()
    if "," not in query:
        query = f"{query}, India"

    try:
        location = geocoder.geocode(query)
    except Exception as exc:
        raise CityResolutionError(f"Geocoding failed for '{city_name}': {exc}") from exc

    if location is None:
        raise CityResolutionError(
            f"Could not find coordinates for '{city_name}'. Try a clearer name (e.g. 'Pune, India')."
        )

    return {
        "lat": float(location.latitude),
        "lon": float(location.longitude),
        "source": "geocode",
        "label": location.address or city_name.strip(),
    }
