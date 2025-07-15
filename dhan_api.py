# dhan_api.py

import requests
from config import DHAN_API_KEY, DHAN_CLIENT_ID, DHAN_ACCESS_TOKEN
from utils import log_message

class DhanTrader:
    def __init__(self):
        self.api_key = DHAN_API_KEY
        self.client_id = DHAN_CLIENT_ID
        self.access_token = DHAN_ACCESS_TOKEN
        self.base_url = "https://api.dhan.co"

        self.headers = {
            "access-token": self.access_token,
            "client-id": self.client_id
        }

    def place_order(self, symbol, quantity, price, side, product_type, order_type, validity="DAY"):
        url = f"{self.base_url}/orders"
        payload = {
            "security_id": symbol,
            "transaction_type": side.upper(),  # BUY / SELL
            "quantity": quantity,
            "order_type": order_type.upper(),  # MARKET / LIMIT
            "price": price,
            "product_type": product_type.upper(),  # INTRADAY / DELIVERY
            "validity": validity
        }

        try:
            response = requests.post(url, headers=self.headers, json=payload)
            if response.status_code == 200:
                log_message(f"Order placed: {symbol} {side} Qty: {quantity}")
                return response.json()
            else:
                log_message(f"Order failed: {response.text}")
                return None
        except Exception as e:
            log_message(f"Order exception: {e}")
            return None

    def get_positions(self):
        url = f"{self.base_url}/positions"
        try:
            response = requests.get(url, headers=self.headers)
            return response.json()
        except Exception as e:
            log_message(f"Error fetching positions: {e}")
            return []

    def exit_position(self, position_id):
        url = f"{self.base_url}/positions/{position_id}/exit"
        try:
            response = requests.post(url, headers=self.headers)
            return response.json()
        except Exception as e:
            log_message(f"Error exiting position {position_id}: {e}")
            return None
