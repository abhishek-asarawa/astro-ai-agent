# lords.py

# Standard Rashi list (0-indexed for modulo math)
RASHIS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", 
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
]

# Rulership mapping: Which planet rules which Rashi
RASHI_RULERS = {
    "Aries": "Mars", "Taurus": "Venus", "Gemini": "Mercury", "Cancer": "Moon",
    "Leo": "Sun", "Virgo": "Mercury", "Libra": "Venus", "Scorpio": "Mars",
    "Sagittarius": "Jupiter", "Capricorn": "Saturn", "Aquarius": "Saturn", "Pisces": "Jupiter"
}

def get_house_lords(lagna_rashi: str) -> dict:
    """
    Calculates the house lordships for a given Lagna.
    Returns a dictionary mapping each planet to the houses it rules.
    """
    try:
        lagna_idx = RASHIS.index(lagna_rashi)
    except ValueError:
        raise ValueError(f"Invalid Rashi: {lagna_rashi}")

    lordships = {
        "Sun": [], "Moon": [], "Mars": [], "Mercury": [],
        "Jupiter": [], "Venus": [], "Saturn": [], "Rahu": [], "Ketu": []
    }

    # Iterate through the 12 houses (1-12)
    for house_offset in range(12):
        house_num = house_offset + 1
        current_rashi_idx = (lagna_idx + house_offset) % 12
        current_rashi = RASHIS[current_rashi_idx]
        
        ruler = RASHI_RULERS[current_rashi]
        lordships[ruler].append(house_num)

    return lordships

# Example output if Lagna is Taurus:
# {'Sun': [4], 'Moon': [3], 'Mars': [7, 12], 'Mercury': [2, 5], 'Jupiter': [8, 11], 'Venus': [1, 6], 'Saturn': [9, 10]}