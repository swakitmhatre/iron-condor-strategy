import time
from utils import (
    log_message,
    should_exit_due_to_market_move,
    check_manual_exit,
    check_force_entry
)
from dhan import Dhan
from position_handler import place_iron_condor, exit_all_positions

def run_strategy():
    log_message("Iron Condor strategy running")

    dhan = Dhan(auth_token="your_dhan_api_token_here")

    log_message("Iron Condor strategy started")

    # Check market time & conditions here (or skip with force_entry)
    if not check_force_entry():
        log_message("Skipping entry — outside valid conditions and no force flag")
        return

    success, positions = place_iron_condor(dhan)

    if not success:
        log_message("Entry failed.")
        return

    entry_time = time.time()
    entry_spot = dhan.get_nifty_spot()

    # Monitor loop
    while True:
        if check_manual_exit():
            log_message("Manual exit flag detected.")
            break

        current_spot = dhan.get_nifty_spot()
        if should_exit_due_to_market_move(entry_spot, current_spot):
            log_message(f"Market moved more than 1%. Entry: {entry_spot}, Now: {current_spot}")
            break

        time.sleep(15)

    exit_all_positions(dhan)
