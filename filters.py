# filters.py

import random
from datetime import datetime, time

def is_time_between(start_str, end_str):
    now = datetime.now().time()
    start = datetime.strptime(start_str, "%H:%M").time()
    end = datetime.strptime(end_str, "%H:%M").time()
    return start <= now <= end

def is_conditions_favorable():
    # Simulated check
    return random.choice([True, True, True, False])
