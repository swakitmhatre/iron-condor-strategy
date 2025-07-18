# dhan.py

import requests
from utils import log_message

class Dhan:
    def __init__(self, auth_token, client_id):
        self.base = "https://api.dhan.co/v2"
        self.headers = {
            "Accept": "application/json",
            "Access-Token": auth_token,
            "Client-Id": client_id,
        }

    def get_nifty_spot(self):
        url = f"{self.base}/market/live/quote"
        params = {
            "exchangeSegment": 0,
            "securityId": 13
        }
        resp = requests.get(url, headers=self.headers, params=params)
        data = resp.json()
        log_message(f"NIFTY LTP API response: {data}")
        if resp.status_code != 200 or data.get("status") == "failed" or "lastTradedPrice" not in data.get("Data", {}):
            raise Exception(f"Fetch NIFTY spot failed: {data}")
        return float(data["Data"]["lastTradedPrice"])
