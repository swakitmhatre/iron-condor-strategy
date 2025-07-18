# dhan.py

import requests
from config import DHAN_ACCESS_TOKEN, DHAN_CLIENT_ID

class Dhan:
    BASE_URL = "https://api.dhan.co"

    def __init__(self):
        self.session = requests.Session()
        self.headers = {
            "access-token": DHAN_ACCESS_TOKEN,
            "client-id": DHAN_CLIENT_ID
        }

    def get_nifty_spot_price(self):
        url = f"{self.BASE_URL}/market/live/quote"
        params = {"securityId": "1333"}  # ✅ Correct security ID for NIFTY 50 Index
        response = self.session.get(url, headers=self.headers, params=params)
        data = response.json()

        if "data" in data and "lastTradedPrice" in data["data"]:
            return float(data["data"]["lastTradedPrice"]) / 100
        else:
            raise Exception(f"Fetch NIFTY spot failed: {data}")
