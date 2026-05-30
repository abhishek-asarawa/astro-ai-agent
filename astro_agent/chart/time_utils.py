"""IST → UTC conversion utilities."""
from datetime import datetime, timedelta


def convert_ist_to_utc(year, month, day, hour, minute):
    """Convert Indian Standard Time (IST) to UTC.

    IST is UTC+5:30. Subtracts 5 hours 30 minutes.
    Returns a dict with year/month/day/hour_utc (decimal hour for Swiss Ephemeris).
    """
    local_time = datetime(year, month, day, hour, minute)
    utc_time = local_time - timedelta(hours=5, minutes=30)

    decimal_hour = utc_time.hour + (utc_time.minute / 60.0) + (utc_time.second / 3600.0)

    return {
        "year": utc_time.year,
        "month": utc_time.month,
        "day": utc_time.day,
        "hour_utc": decimal_hour,
    }
