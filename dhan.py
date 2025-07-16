import requests
import json
from config import DHAN_API_KEY
from utils import log_message

class Dhan:
    def __init__(self, auth_token):
        self.auth_token = auth_token
        self.base_url = "https://api.dhan.co"
        self.headers = {
            "accept": "application/json",
            "access-token": self.auth_token,
            "Dhan-Client-Id": DHAN_API_KEY
        }

    def get_positions(self):
        url = f"{self.base_url}/positions"
        response = requests.get(url, headers=self.headers)
        return response.json()

    def place_order(self, order_data):
        url = f"{self.base_url}/orders"
        response = requests.post(url, json=order_data, headers=self.headers)
        return response.json()

    def exit_order(self, order_id):
        url = f"{self.base_url}/orders/{order_id}/cancel"
        response = requests.delete(url, headers=self.headers)
        return response.status_code == 200

    def get_nifty_spot(self):
        url = f"{self.base_url}/quotes/indices/NSE_NIFTY_50"
        response = requests.get(url, headers=self.headers)
        data = response.json()

        log_message(f"NIFTY spot API response: {json.dumps(data)}")

        if 'lastTradedPrice' not in data:
            raise ValueError(f"Could not fetch NIFTY spot. Response: {data}")

        return float(data['lastTradedPrice']) / 100  # Dhan returns price in paisa

    def get_option_chain(self, symbol, expiry_date):
        url = f"{self.base_url}/instruments/option-chain"
        params = {
            "symbol": symbol,
            "expiry": expiry_date
        }
        response = requests.get(url, params=params, headers=self.headers)
        return response.json()
