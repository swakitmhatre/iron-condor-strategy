# dhan.py

import requests
from utils import log_message
from config import DHAN_API_KEY, DHAN_ACCESS_TOKEN, DHAN_CLIENT_ID

class DhanAPI:
    def __init__(self):
        self.base = "https://api.dhan.co"
        self.headers = {
            "Accept": "application/json",
            "access-token": DHAN_ACCESS_TOKEN,
            "client-id": DHAN_CLIENT_ID
        }

    def get_nifty_spot(self):
        url = f"{self.base}/marketfeed/ltp"
        body = {
            "instruments": [
                {
                    "exchangeSegment": "NSE_INDEX",
                    "instrument": "Nifty 50"
                }
            ]
        }
        try:
            resp = requests.post(url, headers=self.headers, json=body, timeout=5)
            data = resp.json()
            log_message(f"NIFTY LTP API response: {data}")
            ltp = data["data"]["NSE_INDEX|Nifty 50"]["lastTradedPrice"]
            return float(ltp)
        except Exception as e:
            raise Exception(f"Fetch NIFTY spot failed: {data}")

    def place_order(self, order_data):
        url = f"{self.base}/orders"
        try:
            response = requests.post(url, headers=self.headers, json=order_data, timeout=5)
            log_message(f"Order response: {response.status_code}, {response.text}")
            return response.json()
        except Exception as e:
            raise Exception(f"Place order failed: {str(e)}")

    def exit_all_positions(self):
        url = f"{self.base}/positions/intraday"
        try:
            response = requests.get(url, headers=self.headers, timeout=5)
            positions = response.json().get("data", [])
            log_message(f"Fetched open positions: {positions}")
            for position in positions:
                exit_order = {
                    "transactionType": "SELL" if position["buyQty"] > position["sellQty"] else "BUY",
                    "exchangeSegment": position["exchangeSegment"],
                    "productType": position["productType"],
                    "orderType": "MARKET",
                    "instrument": position["tradingSymbol"],
                    "quantity": abs(position["buyQty"] - position["sellQty"]),
                    "price": 0,
                    "triggerPrice": 0,
                    "validity": "DAY"
                }
                self.place_order(exit_order)
        except Exception as e:
            log_message(f"Error exiting positions: {e}")
