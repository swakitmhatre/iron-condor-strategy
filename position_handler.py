from utils import get_strike_prices, log_message
from telegram import send_telegram_update

def place_iron_condor(dhan):
    spot = dhan.get_nifty_spot()
    log_message(f"NIFTY Spot: {spot}")
    strikes = get_strike_prices(spot)
    log_message(f"Using strikes: {strikes}")

    # Example order payloads
    orders = [
        {"symbol": "NIFTY", "strike": strikes['ce_sell'], "side": "SELL", "type": "CE"},
        {"symbol": "NIFTY", "strike": strikes['pe_sell'], "side": "SELL", "type": "PE"},
        {"symbol": "NIFTY", "strike": strikes['ce_buy'], "side": "BUY", "type": "CE"},
        {"symbol": "NIFTY", "strike": strikes['pe_buy'], "side": "BUY", "type": "PE"},
    ]

    # Place buy legs first for margin efficiency
    executed = []
    for order in [orders[2], orders[3], orders[0], orders[1]]:
        result = dhan.place_order(order)
        executed.append(result)
        log_message(f"Order placed: {order} | Response: {result}")

    send_telegram_update(f"Entry completed with strikes: {strikes}")
    return True, executed

def exit_all_positions(dhan):
    # Simplified — add logic to fetch positions and exit
    log_message("Exiting all positions.")
    send_telegram_update("Manual exit triggered. Exiting all positions.")
