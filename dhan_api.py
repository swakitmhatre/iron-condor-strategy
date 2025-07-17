# dhan_api.py

import requests
from config import DHAN_API_KEY

class DhanTrader:
    def __init__(self):
        self.base_url = "https://api.dhan.co"
        self.headers = {
            "Authorization": f"Bearer {DHAN_API_KEY}",
            "Content-Type": "application/json"
        }

    def get_nifty_spot(self):
        url = f"{self.base_url}/market/live/quotes/indices/NSE_INDEX/NIFTY_50"
        response = requests.get(url, headers=self.headers)
        data = response.json()
        if 'lastTradedPrice' in data:
            return float(data['lastTradedPrice']) / 100
        raise ValueError(f"Could not fetch NIFTY spot. Response: {data}")

    def get_margin_required(self, orders):
        url = f"{self.base_url}/margin/multileg"
        payload = {"orders": orders}
        res = requests.post(url, headers=self.headers, json=payload)
        return res.json()

    def place_order(self, order):
        url = f"{self.base_url}/orders"
        res = requests.post(url, headers=self.headers, json=order)
        return res.json()

    def exit_position(self, order_id):
        url = f"{self.base_url}/orders/{order_id}/cancel"
        res = requests.post(url, headers=self.headers)
        return res.json()
