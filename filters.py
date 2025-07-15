# filters.py

from datetime import datetime
import requests

def is_time_between(start_time_str, end_time_str):
    """Check if current time is between start and end time strings in HH:MM format."""
    now = datetime.now().time()
    start = datetime.strptime(start_time_str, "%H:%M").time()
    end = datetime.strptime(end_time_str, "%H:%M").time()
    return start <= now <= end

def is_conditions_favorable():
    """
    Define logic to filter out unfavorable market days.
    Returns True if favorable, False otherwise.
    Includes:
    - Avoid gap-up/gap-down
    - Avoid high IV
    - Avoid heavy news day (optional if using calendar)
    """
    try:
        # Example filter: avoid large gap-up or gap-down
        previous_close = get_previous_day_close()
        current_open = get_current_day_open()

        if previous_close and current_open:
            gap_percent = abs((current_open - previous_close) / previous_close) * 100
            if gap_percent > 0.75:
                return False

        # Placeholder: add more filters like IV, news day, etc., if needed
        return True

    except Exception:
        return False  # On error, assume not favorable

def get_previous_day_close():
    """Fetch previous close of NIFTY from a public API or mock."""
    try:
        # Replace with actual data source if available
        return 22450.00  # Mock
    except:
        return None

def get_current_day_open():
    """Fetch today's open price of NIFTY from a public API or mock."""
    try:
        # Replace with actual data source if available
        return 22390.00  # Mock
    except:
        return None
