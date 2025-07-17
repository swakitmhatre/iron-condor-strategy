import requests
import json
from datetime import datetime

class Dhan:
    def __init__(self, auth_token):
        self.auth_token = auth_token
        self.base_url = "https://api.dhan.co"
        self.headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.auth_token}"
        }

    def get_nifty_spot(self):
        url = f"{self.base_url}/market/feed/indices/NSE_NIFTY"
        response = requests.get(url, headers=self.headers)
        data = response.json()

        from utils import log_message
        log_message(f"NIFTY spot API response: {json.dumps(data)}")

        if 'lastTradedPrice' in data:
            return float(data['lastTradedPrice']) / 100  # Dhan returns price in paisa
        raise ValueError(f"Could not fetch NIFTY spot. Response: {data}")

    def place_order(self, payload):
        url = f"{self.base_url}/orders"
        response = requests.post(url, headers=self.headers, json=payload)
        return response.json()

    def get_order_status(self, order_id):
        url = f"{self.base_url}/orders/{order_id}"
        response = requests.get(url, headers=self.headers)
        return response.json()

    def get_margin_required(self, legs):
        url = f"{self.base_url}/margin"
        response = requests.post(url, headers=self.headers, json={"legs": legs})
        return response.json()

    def get_positions(self):
        url = f"{self.base_url}/positions"
        response = requests.get(url, headers=self.headers)
        return response.json()
