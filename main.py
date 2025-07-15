# main.py

import time
import os
import datetime as dt
from utils import *
from config import *
from telegram_bot import send_telegram_message


def main():
    send_telegram_message("\u2705 Iron Condor Strategy Started")
    log("Strategy started")

    if not is_market_open():
        log("Market closed, exiting.")
        send_telegram_message("\u274C Market is closed. Strategy exiting.")
        return

    if not is_time_between(entry_start_time, entry_end_time):
        log("Outside entry window, exiting.")
        send_telegram_message("\u274C Outside entry window. Strategy exiting.")
        return

    if os.path.exists("stop.flag"):
        log("Manual stop.flag detected. Exiting.")
        send_telegram_message("\u274C Manual stop.flag found. Exiting strategy.")
        return

    if not check_market_conditions():
        if os.path.exists("force_entry.flag"):
            log("Force entry flag found. Skipping market condition checks.")
            send_telegram_message("\u26a0\ufe0f Force entry flag active. Ignoring market conditions.")
        else:
            log("Unfavorable market conditions. Exiting.")
            send_telegram_message("\u274C Unfavorable market conditions. No trade taken.")
            return

    instrument, strikes = get_atm_strikes()
    log(f"Underlying: {instrument}, Strikes: {strikes}")

    buy_order_ids = place_buy_legs(instrument, strikes)
    if not buy_order_ids:
        log("Buy legs failed. Aborting.")
        send_telegram_message("\u274C Buy legs placement failed.")
        return
    time.sleep(2)

    sell_order_ids = place_sell_legs(instrument, strikes)
    if not sell_order_ids:
        log("Sell legs failed. Attempting to exit buy legs.")
        square_off_orders(buy_order_ids)
        send_telegram_message("\u274C Sell legs failed. Buy legs squared off.")
        return

    log("All positions placed successfully")
    send_telegram_message("\u2705 Iron Condor placed successfully")

    entry_time = dt.datetime.now().strftime("%H:%M:%S")
    log(f"Entry Time: {entry_time}")
    track_mtm_and_exit(instrument, buy_order_ids, sell_order_ids)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"Exception: {str(e)}")
        send_telegram_message(f"\u274C Strategy Error: {str(e)}")
        try:
            square_off_all_positions()
        except:
            log("Emergency exit failed")
        send_telegram_message("\u26a0\ufe0f Emergency exit attempted. Strategy stopped.")
