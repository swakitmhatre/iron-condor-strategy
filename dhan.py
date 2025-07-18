# dhan.py

import requests
from utils import log_message

class Dhan:
    def __init__(self, auth_token, client_id):
        self.base_url = "https://api.dhan.co"
        self.headers = {
            "Accept": "application/json",
            "Access-Token": auth_token,
            "Client-Id": client_id,
        }

    def get_nifty_spot(self):
        url = f"{self.base_url}/market/quotes/instrument/quote"
        params = {
            "securityId": "1333",  # NIFTY 50 index security ID from Dhan
            "exchangeSegment": "NSE_INDEX",
            "instrumentType": "INDEX"
        }
        response = requests.get(url, headers=self.headers, params=params)
        data = response.json()

        log_message(f"NIFTY LTP API response: {data}")

        try:
            ltp = data["lastTradedPrice"]
            return float(ltp) / 100
        except Exception:
            raise Exception(f"Fetch NIFTY spot failed: {data}")
