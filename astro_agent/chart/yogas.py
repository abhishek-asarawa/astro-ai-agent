# yogas.py

EXALTATION_MAP = {
    "Sun": "Aries", "Moon": "Taurus", "Mars": "Capricorn",
    "Mercury": "Virgo", "Jupiter": "Cancer", "Venus": "Pisces", "Saturn": "Libra"
}

DEBILITATION_MAP = {
    "Sun": "Libra", "Moon": "Scorpio", "Mars": "Cancer",
    "Mercury": "Pisces", "Jupiter": "Capricorn", "Venus": "Virgo", "Saturn": "Aries"
}

OWN_SIGN_MAP = {
    "Sun": ["Leo"], "Moon": ["Cancer"], "Mars": ["Aries", "Scorpio"],
    "Mercury": ["Gemini", "Virgo"], "Jupiter": ["Sagittarius", "Pisces"],
    "Venus": ["Taurus", "Libra"], "Saturn": ["Capricorn", "Aquarius"]
}

def get_planetary_dignity(planet: str, rashi: str) -> list:
    """
    Evaluates the basic dignity of a planet based on its sign.
    Returns a list of string tags (e.g., ["[EXALTED]"]).
    """
    tags = []
    
    # Rahu and Ketu are shadows and skip standard dignity rules in this basic pass
    if planet in ["Rahu", "Ketu"]:
        return tags

    if EXALTATION_MAP.get(planet) == rashi:
        tags.append("[EXALTED]")
    elif DEBILITATION_MAP.get(planet) == rashi:
        tags.append("[DEBILITATED]")
    elif rashi in OWN_SIGN_MAP.get(planet, []):
        tags.append("[OWN SIGN / SWA-KSHETRA]")
        
    return tags

def apply_tags_to_chart(planet_data: dict) -> dict:
    """
    Takes a dictionary of planets and their signs, appends tags.
    Format input: {"Mars": "Capricorn", "Venus": "Aquarius"}
    """
    tagged_data = {}
    for planet, rashi in planet_data.items():
        tags = get_planetary_dignity(planet, rashi)
        tag_str = " ".join(tags) if tags else "[NEUTRAL]"
        tagged_data[planet] = f"{rashi} {tag_str}"
        
    return tagged_data