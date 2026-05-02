# Constants for Vedic Astrology
RASHIS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", 
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
]

NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra", 
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni", 
    "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha", "Mula", 
    "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha", 
    "Purva Bhadrapada", "Uttara Bhadrapada", "Revati"
]

def get_vedic_details(longitude):
    """Maps 360° longitude to Vedic Rashi and Nakshatra."""
    # Rashi calculation
    rashi_idx = int(longitude / 30)
    deg_in_sign = longitude % 30
    
    # Nakshatra calculation (13.3333° per nakshatra)
    nak_idx = int(longitude / (360 / 27))
    
    return {
        "rashi": RASHIS[rashi_idx % 12],
        "degrees": round(deg_in_sign, 2),
        "nakshatra": NAKSHATRAS[nak_idx % 27]
    }