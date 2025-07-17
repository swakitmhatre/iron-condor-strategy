import requests
from config import DHAN_API_KEY, DHAN_ACCESS_TOKEN
from utils import log_message

class DhanTrader:
    def __init__(self):
        self.base_url = "https://api.dhan.co"
        self.headers = {
            "accept": "application/json",
            "access-token": DHAN_ACCESS_TOKEN,
            "Dhan-Client-Id": DHAN_API_KEY
        }

    def get_nifty_spot(self):
        url = f"{self.base_url}/market/live/quotes/indices/NSE_INDEX/NIFTY_50"
        response = requests.get(url, headers=self.headers)
        log_message(f"NIFTY spot API response: {response.text}")

        try:
            data = response.json()
            return float(data["lastTradedPrice"]) / 100  # Dhan returns price in paise
        except (KeyError, ValueError, TypeError) as e:
            raise ValueError(f"Could not fetch NIFTY spot. Response: {data}") from e

    def place_order(self, order_data):
        url = f"{self.base_url}/orders"
        response = requests.post(url, headers=self.headers, json=order_data)
        log_message(f"Order Placement Response: {response.text}")
        return response.json()

    def exit_order(self, order_id):
        url = f"{self.base_url}/orders/{order_id}"
        response = requests.delete(url, headers=self.headers)
        log_message(f"Order Exit Response: {response.text}")
        return response.status_code == 200

    def get_positions(self):
        url = f"{self.base_url}/positions"
        response = requests.get(url, headers=self.headers)
        log_message(f"Positions Response: {response.text}")
        return response.json()

    def get_mtm(self):
        url = f"{self.base_url}/positions"
        response = requests.get(url, headers=self.headers)
        data = response.json()
        mtm = 0.0
        for pos in data:
            try:
                mtm += float(pos.get("pnl", 0.0))
            except:
                continue
        return mtm
