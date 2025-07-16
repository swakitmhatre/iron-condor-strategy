# dhan.py

import requests
from config import DHAN_API_KEY

class Dhan:
    def __init__(self, auth_token):
        self.auth_token = auth_token
        self.base_url = "https://api.dhan.co"
        self.headers = {
            "accept": "application/json",
            "access-token": self.auth_token,
            "Dhan-Client-Id": DHAN_API_KEY
        }

    def get_nifty_spot(self):
        url = f"{self.base_url}/quotes/indices/NSE_INDEX_NIFTY"
        response = requests.get(url, headers=self.headers)
        data = response.json()
        return float(data['lastTradedPrice']) / 100  # Dhan returns price in paisa

    def place_order(self, symbol, strike, side):
        # Simulated order placement (for paper trading)
        order = {
            "symbol": symbol,
            "strike": strike,
            "side": side,
            "id": f"{symbol}-{strike}-{side}"
        }
        return order
