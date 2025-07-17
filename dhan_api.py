# dhan_api.py

import requests
from config import DHAN_BASE_URL, DHAN_API_TOKEN

class DhanTrader:
    def __init__(self):
        self.base_url = DHAN_BASE_URL
        self.headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {DHAN_API_TOKEN}"
        }

    def get_nifty_spot(self):
        url = f"{self.base_url}/market/live/quotes/indices/NSE_INDEX%7CNifty%2050"
        res = requests.get(url, headers=self.headers)
        data = res.json()
        if res.status_code == 200 and 'lastTradedPrice' in data:
            return data['lastTradedPrice'] / 100
        raise ValueError(f"Fetch spot failed: {data}")
