import requests
from utils import log_message

class Dhan:
    def __init__(self, auth_token):
        self.auth_token = auth_token
        self.base_url = "https://api.dhan.co"
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "access-token": self.auth_token
        }

    def place_order(self, symbol, action, quantity, order_type="MARKET"):
        log_message(f"Placing order: {action} {symbol} x{quantity}")
        # Real order placement logic would go here
        return True

    def get_nifty_spot(self):
        """
        Fetches NIFTY spot price from public NSE API.
        """
        try:
            response = requests.get("https://www.niftyindices.com/Indices/ind_nifty50.json", timeout=5)
            data = response.json()
            spot = float(data['data'][0]['lastPrice'].replace(',', ''))
            log_message(f"NIFTY spot from public source: {spot}")
            return spot
        except Exception as e:
            log_message(f"Failed to fetch NIFTY spot from public API: {e}")
            raise ValueError("Cannot fetch NIFTY spot from fallback source.")
