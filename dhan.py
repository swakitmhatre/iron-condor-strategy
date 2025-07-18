# dhan.py

import requests
from utils import log_message

class Dhan:
    def __init__(self, auth_token, client_id):
        self.base = "https://api.dhan.co/v2"
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "access-token": auth_token,
            "client-id": client_id,
        }

    def get_nifty_spot(self):
        url = f"{self.base}/marketfeed/ltp"
        body = {"NSE_INDEX": [2]}  # 2 is Nifty 50 instrument ID :contentReference[oaicite:8]{index=8}
        resp = requests.post(url, headers=self.headers, json=body, timeout=5)
        data = resp.json()
        log_message(f"NIFTY LTP API response: {data}")
        if resp.status_code != 200 or data.get("status") != "success" or "NSE_INDEX" not in data.get("data", {}):
            raise Exception(f"Fetch NIFTY spot failed: {data}")
        ltp = data["data"]["NSE_INDEX"].get("2", {}).get("last_price")
        if ltp is None:
            raise Exception(f"Missing last_price in response: {data}")
        return float(ltp)
