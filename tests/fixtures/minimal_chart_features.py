"""Minimal chart-features dict for characterization / prompt snapshot tests."""

MINIMAL_FEATURES = {
    "lagna": {"rashi": "Aries", "degrees": 10.0},
    "planets": {
        "Sun": {"rashi": "Taurus", "degrees": 5.0, "nakshatra": "Krittika"},
        "Moon": {"rashi": "Cancer", "degrees": 12.0, "nakshatra": "Pushya"},
        "Mars": {"rashi": "Aries", "degrees": 8.0, "nakshatra": "Ashwini"},
        "Mercury": {"rashi": "Gemini", "degrees": 20.0, "nakshatra": "Punarvasu"},
        "Jupiter": {"rashi": "Sagittarius", "degrees": 15.0, "nakshatra": "Purva Ashadha"},
        "Venus": {"rashi": "Libra", "degrees": 3.0, "nakshatra": "Chitra"},
        "Saturn": {"rashi": "Capricorn", "degrees": 25.0, "nakshatra": "Dhanishta"},
        "Rahu": {"rashi": "Aquarius", "degrees": 10.0, "nakshatra": "Shatabhisha"},
        "Ketu": {"rashi": "Leo", "degrees": 10.0, "nakshatra": "Magha"},
    },
    "planetary_dignities": {
        "Sun": "[NEUTRAL]",
        "Moon": "[OWN]",
        "Mars": "[OWN]",
        "Mercury": "[OWN]",
        "Jupiter": "[OWN]",
        "Venus": "[OWN]",
        "Saturn": "[OWN]",
        "Rahu": "[NEUTRAL]",
        "Ketu": "[NEUTRAL]",
    },
    "house_lordships": {
        "Mars": [1, 8],
        "Venus": [2, 7],
        "Mercury": [3, 6],
        "Moon": [4],
        "Sun": [5],
        "Jupiter": [9, 12],
        "Saturn": [10, 11],
    },
    "active_dasha": {"dasha": "Jupiter", "start": "2020-01-01", "end": "2036-01-01"},
    "next_dasha": {"dasha": "Saturn", "start": "2036-01-01", "end": "2055-01-01"},
    "active_antardasha": {"dasha": "Saturn", "start": "2024-01-01", "end": "2026-09-01"},
    "next_antardasha": {"dasha": "Mercury", "start": "2026-09-01", "end": "2029-02-01"},
    "dasha_timeline": [
        {
            "dasha": "Jupiter",
            "start": "2020-01-01",
            "end": "2036-01-01",
            "is_birth_dasha": True,
        },
        {
            "dasha": "Saturn",
            "start": "2036-01-01",
            "end": "2055-01-01",
            "is_birth_dasha": False,
        },
    ],
}
