import requests
import json
from utils import log_message

class Dhan:
    def __init__(self, auth_token: str):
        self.base_url = "https://api.dhan.co"
        self.headers = {
            "accept": "application/json",
            "authorization": f"Bearer {auth_token}"
        }

    def get_nifty_spot(self):
        # ✅ Final confirmed endpoint
        url = f"{self.base_url}/quotes/indices/NSE_NIFTY_50"
        response = requests.get(url, headers=self.headers)
        data = response.json()
        log_message(f"NIFTY spot API response: {json.dumps(data)}")

        try:
            return float(data['lastTradedPrice']) / 100
        except KeyError:
            raise ValueError(f"Could not fetch NIFTY spot. Response: {data}")

    def place_order(self, order_payload):
        url = f"{self.base_url}/orders"
        response = requests.post(url, json=order_payload, headers=self.headers)
        return response.json()

    def get_required_margin(self, payload):
        url = f"{self.base_url}/margin/calculator"
        response = requests.post(url, json=payload, headers=self.headers)
        return response.json()
