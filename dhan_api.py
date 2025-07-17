# dhan_api.py

import requests
from config import DHAN_BASE_URL, DHAN_API_TOKEN
from utils import log_message

class DhanTrader:
    def __init__(self):
        self.base_url = DHAN_BASE_URL
        self.headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "access-token": DHAN_API_TOKEN  # use header as per docs
        }

    def get_nifty_spot(self):
        """
        Fetch the live NIFTY 50 index LTP using Dhan's marketfeed API.
        Uses security ID 13 for Nifty 50. Referenced from Dhan community and docs. :contentReference[oaicite:1]{index=1}
        """
        SECURITY_ID = 13
        url = f"{self.base_url}/v2/marketfeed/ltp"
        payload = {"NSE_IDX": [SECURITY_ID], "NSE_FNO": []}
        resp = requests.post(url, json=payload, headers=self.headers)
        data = resp.json()
        log_message(f"NIFTY LTP API response: {data}")

        if resp.status_code == 200 and "data" in data:
            d = data["data"].get("NSE_IDX", {})
            if str(SECURITY_ID) in d:
                return d[str(SECURITY_ID)]["last_price"]
        raise ValueError(f"Fetch NIFTY spot failed: {data}")
