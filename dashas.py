# dashas.py
import datetime

# Dasha sequence and their total durations in years
DASHA_SEQUENCE = [
    ("Ketu", 7), ("Venus", 20), ("Sun", 6), ("Moon", 10), 
    ("Mars", 7), ("Rahu", 18), ("Jupiter", 16), ("Saturn", 19), ("Mercury", 17)
]

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
    
    timeline.append({
        "dasha": first_lord,
        "start": current_date.strftime("%Y-%m-%d"),
        "end": end_date.strftime("%Y-%m-%d"),
        "is_birth_dasha": True
    })
    
    current_date = end_date
    
    # Calculate the remaining Dashas to complete a full 120-year cycle
    for offset in range(1, 9):
        idx = (dasha_start_index + offset) % 9
        lord, total_years = DASHA_SEQUENCE[idx]
        
        duration_days = total_years * 365.25
        end_date = current_date + datetime.timedelta(days=duration_days)
        
        timeline.append({
            "dasha": lord,
            "start": current_date.strftime("%Y-%m-%d"),
            "end": end_date.strftime("%Y-%m-%d"),
            "is_birth_dasha": False
        })
        
        current_date = end_date

    return timeline

def format_dasha_timeline(timeline: list) -> str:
    """Formats the timeline list into a readable string block for the AI prompt."""
    output = ["--- VIMSHOTTARI DASHA TIMELINE ---"]
    for d in timeline:
        birth_tag = "(Birth Dasha)" if d['is_birth_dasha'] else ""
        output.append(f"{d['dasha']} Mahadasha: {d['start']} to {d['end']} {birth_tag}")
    return "\n".join(output)