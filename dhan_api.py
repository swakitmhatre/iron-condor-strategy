import requests
import json
from config import DHAN_BASE_URL, DHAN_AUTH_TOKEN
from utils import log_message

class DhanTrader:
    def __init__(self):
        self.base_url = DHAN_BASE_URL
        self.headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {DHAN_AUTH_TOKEN}"
        }

    def get_nifty_spot(self):
        try:
            url = f"{self.base_url}/market/live/quotes/indices/NSE_INDEX%7CNifty%2050"
            response = requests.get(url, headers=self.headers)
            data = response.json()
            log_message(f"NIFTY spot API response: {data}")
            return float(data['lastTradedPrice']) / 100
        except Exception as e:
            raise ValueError(f"Could not fetch NIFTY spot. Response: {data}")
