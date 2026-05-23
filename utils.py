from datetime import datetime, timedelta

def convert_ist_to_utc(year, month, day, hour, minute):
    """
    Converts Indian Standard Time (IST) to UTC.
    IST is UTC + 5:30. To get UTC, we subtract 5 hours and 30 minutes.
    """
    local_time = datetime(year, month, day, hour, minute)
    utc_time = local_time - timedelta(hours=5, minutes=30)
    
    # Return values needed for Swiss Ephemeris
    # Decimal hour is required (e.g., 7:30 AM = 7.5)
    decimal_hour = utc_time.hour + (utc_time.minute / 60.0) + (utc_time.second / 3600.0)
    
    return {
        "year": utc_time.year,
        "month": utc_time.month,
        "day": utc_time.day,
        "hour_utc": decimal_hour
    }

# Re-export for backward compatibility
from cities import CITY_COORDINATES  # noqa: F401