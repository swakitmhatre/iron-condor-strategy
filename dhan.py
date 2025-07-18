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
    body = {
        "instruments": [
            {
                "exchangeSegment": "NSE_INDEX",
                "instrument": "Nifty 50"
            }
        ]
    }
    resp = requests.post(url, headers=self.headers, json=body, timeout=5)
    data = resp.json()
    log_message(f"NIFTY LTP API response: {data}")
    
    try:
        ltp = data["data"]["NSE_INDEX|Nifty 50"]["lastTradedPrice"]
        return float(ltp)
    except Exception as e:
        raise Exception(f"Fetch NIFTY spot failed: {data}")
