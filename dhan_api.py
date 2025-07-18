# dhan_api.py
# dhan_api.py

import requests
from config import DHAN_API_TOKEN, DHAN_CLIENT_ID, DHAN_BASE_URL
from instruments import get_next_week_expiry
from telegram_alerts import send_telegram_message

class Dhan:
    def __init__(self):
        self.token = DHAN_API_TOKEN
        self.client_id = DHAN_CLIENT_ID
        self.headers = {
            "accept": "application/json",
            "access-token": self.token,
            "client-id": self.client_id,
        }

    def get_nifty_ltp(self):
        url = f"{DHAN_BASE_URL}/market/feed/indices"
        res = requests.get(url, headers=self.headers, params={"index": "NIFTY"})
        data = res.json()
        return float(data["ltp"]) if "ltp" in data else None

    def place_order(self, symbol, qty, side):
        payload = {
            "symbol": symbol,
            "quantity": qty,
            "side": side,
            "orderType": "MARKET",
            "productType": "INTRADAY",
        }
        res = requests.post(f"{DHAN_BASE_URL}/orders", headers=self.headers, json=payload)
        return res.status_code == 200

    def get_positions(self):
        res = requests.get(f"{DHAN_BASE_URL}/positions", headers=self.headers)
        return res.json()

    def exit_all(self):
        positions = self.get_positions()
        for pos in positions:
            self.place_order(pos['symbol'], pos['quantity'], "SELL" if pos["buyQty"] > 0 else "BUY")

def log_message(msg):
    print(msg)
    send_telegram_message(msg)

'''import requests
from config import DHAN_BASE_URL, DHAN_API_TOKEN
from utils import log_message

class DhanTrader:
    def __init__(self):
        self.base_url = DHAN_BASE_URL
        self.headers = {
            "accept": "application/json",
            "access-token": DHAN_API_TOKEN
        }

    def get_nifty_spot(self):
        """
        Fetch NIFTY 50 live LTP using marketfeed/ltp endpoint.
        Security ID 13 is used for NIFTY 50.
        """
        SECURITY_ID = 13
        url = f"{self.base_url}/v2/marketfeed/ltp"
        payload = {
            "NSE_IDX": [SECURITY_ID],
            "NSE_FNO": []
        }

        try:
            response = requests.post(url, json=payload, headers=self.headers)
            data = response.json()
            log_message(f"NIFTY LTP API response: {data}")

            if response.status_code == 200 and "data" in data:
                if "NSE_IDX" in data["data"]:
                    index_data = data["data"]["NSE_IDX"]
                    if str(SECURITY_ID) in index_data:
                        return index_data[str(SECURITY_ID)]["last_price"]
            raise ValueError(f"Fetch NIFTY spot failed: {data}")
        except Exception as e:
            raise ValueError(f"Fetch spot failed: {str(e)}")'''
