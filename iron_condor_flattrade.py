"""
Iron Condor Strategy Script for Flattrade (NIFTY 50)
Author: ChatGPT
Features:
- Headless token generation via Selenium (manual OTP input required)
- Automatic next week expiry detection
- ATM+9 (buy) and ATM+11 (sell) strike construction
- Entry: Buy legs first, then Sell legs
- MTM tracking (target = 0.25% of margin per lot)
- Dynamic margin calculation
- Logging of entry, MTM trigger, and exit
"""

import os
import time
import json
import math
import csv
import requests
import datetime
import threading
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

# ---------------------------- CONFIGURATION ---------------------------- #
api_key = '5a98658739d3414e85d55c51dc7b2646'
api_secret = '5a98658739d3414e85d55c51dc7b2646'
base_url = 'https://api.flattrade.in'

user_id = input("Enter your Flattrade User ID: ")
password = input("Enter your Flattrade Password: ")
lot_multiplier = int(input("Enter number of lots to trade: "))

symbol = "NIFTY"
lot_size = 50  # NIFTY lot size
strike_gap = 50
mtm_target_pct = 0.25 / 100  # 0.25%
log_file = "iron_condor_log.csv"

# ---------------------------- TOKEN GENERATION ---------------------------- #
def generate_token():
    try:
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        driver = webdriver.Chrome(options=chrome_options)

        driver.get("https://api.flattrade.in/trade/login")
        time.sleep(2)

        driver.find_element(By.NAME, "userid").send_keys(user_id)
        driver.find_element(By.NAME, "password").send_keys(password)
        input("Enter OTP manually and press Enter here once logged in... ")

        cookies = driver.get_cookies()
        token = None
        for c in cookies:
            if c['name'] == 'encToken':
                token = c['value']
                break

        driver.quit()
        if token:
            print("✅ Token generated successfully.")
            return token
        else:
            raise Exception("❌ Token not found in cookies.")
    except Exception as e:
        print(f"❌ Token generation failed: {e}")
        exit(1)

# ---------------------------- SYMBOL UTILITIES ---------------------------- #
def get_next_week_expiry():
    today = datetime.date.today()
    next_thursday = today + datetime.timedelta((3 - today.weekday()) % 7 + 7)
    return next_thursday.strftime("%d%b%Y").upper()

def get_ltp(token, tradingsymbol):
    try:
        url = f"{base_url}/trade/ltp"
        headers = {"Authorization": f"Bearer {token}"}
        payload = {"exchange": "NFO", "tradingsymbol": tradingsymbol}
        r = requests.post(url, headers=headers, json=payload)
        r.raise_for_status()
        return float(r.json()['data']['ltp'])
    except Exception as e:
        print(f"❌ Failed to fetch LTP for {tradingsymbol}: {e}")
        return 0

def get_spot_price(token):
    try:
        url = f"{base_url}/trade/ltp"
        headers = {"Authorization": f"Bearer {token}"}
        payload = {"exchange": "NSE", "tradingsymbol": symbol}
        r = requests.post(url, headers=headers, json=payload)
        r.raise_for_status()
        return float(r.json()['data']['ltp'])
    except Exception as e:
        print(f"❌ Failed to fetch spot price: {e}")
        exit(1)

def construct_symbol(strike, opt_type, expiry):
    return f"NIFTY{expiry}{int(strike)}{opt_type}"

def get_required_margin(token, tradingsymbol):
    try:
        url = f"{base_url}/margin"
        headers = {"Authorization": f"Bearer {token}"}
        payload = {"exchange": "NFO", "tradingsymbol": tradingsymbol, "quantity": lot_size}
        r = requests.post(url, headers=headers, json=payload)
        r.raise_for_status()
        return float(r.json()['data']['total'])
    except Exception as e:
        print(f"❌ Failed to fetch margin for {tradingsymbol}: {e}")
        return 0

# ---------------------------- STRATEGY LOGIC ---------------------------- #
def place_order(token, symbol, side):
    try:
        url = f"{base_url}/placeorder"
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "exchange": "NFO",
            "tradingsymbol": symbol,
            "transaction_type": side,
            "quantity": lot_size * lot_multiplier,
            "order_type": "MKT",
            "product": "MIS",
            "price": 0,
            "trigger_price": 0,
            "validity": "DAY",
        }
        r = requests.post(url, headers=headers, json=payload)
        r.raise_for_status()
        print(f"✅ Order placed: {side} {symbol}")
        return r.json()
    except Exception as e:
        print(f"❌ Order placement failed for {side} {symbol}: {e}")
        return {}

def log_event(event_type, data):
    file_exists = os.path.isfile(log_file)
    with open(log_file, 'a', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Event", "Time", "Details"])
        writer.writerow([event_type, datetime.datetime.now(), data])

def run_strategy(token):
    expiry = get_next_week_expiry()
    spot = get_spot_price(token)
    atm_strike = int(round(spot / strike_gap) * strike_gap)

    strikes = {
        "buy_ce": construct_symbol(atm_strike + 9 * strike_gap, "CE", expiry),
        "buy_pe": construct_symbol(atm_strike - 9 * strike_gap, "PE", expiry),
        "sell_ce": construct_symbol(atm_strike + 11 * strike_gap, "CE", expiry),
        "sell_pe": construct_symbol(atm_strike - 11 * strike_gap, "PE", expiry),
    }

    print("Selected Strikes:", strikes)

    # Margin calculation
    total_margin = 0
    for s in strikes.values():
        margin = get_required_margin(token, s)
        total_margin += margin

    total_margin *= lot_multiplier
    mtm_target = mtm_target_pct * total_margin
    print(f"Total margin: ₹{total_margin:.2f} | MTM Target: ₹{mtm_target:.2f}")

    # Entry
    log_event("ENTRY_ATTEMPT", str(strikes))
    for leg in ["buy_ce", "buy_pe"]:
        place_order(token, strikes[leg], "BUY")
    time.sleep(0.5)
    for leg in ["sell_ce", "sell_pe"]:
        place_order(token, strikes[leg], "SELL")
    log_event("ENTRY_SUCCESS", f"{strikes}")

    # MTM Tracking Loop
    initial = 0
    while True:
        current = 0
        for leg in strikes:
            ltp = get_ltp(token, strikes[leg])
            current += ltp * lot_size * lot_multiplier * (1 if 'buy' in leg else -1)
        mtm = -current
        print(f"[MTM] {mtm:.2f}", end='\r')
        if mtm >= mtm_target:
            log_event("MTM TARGET HIT", f"MTM: ₹{mtm:.2f} >= Target ₹{mtm_target:.2f}")
            break
        time.sleep(0.025)

    for leg in ["sell_ce", "sell_pe"]:
        place_order(token, strikes[leg], "BUY")
    log_event("EXIT", f"Sell legs exited")

# ---------------------------- RUN ---------------------------- #
if __name__ == '__main__':
    session_token = generate_token()
    run_strategy(session_token)
