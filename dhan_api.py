# dhan_api.py

import requests
import json

class DhanTrader:
    def __init__(self, api_key, client_id):
        self.api_key = api_key
        self.client_id = client_id
        self.base_url = "https://api.dhan.co"
        self.headers = {
            "accept": "application/json",
            "access-token": self.api_key,
            "Content-Type": "application/json"
        }

    def get_holdings(self):
        url = f"{self.base_url}/positions"
        response = requests.get(url, headers=self.headers)
        return response.json()

    def place_order(self, symbol, quantity, transaction_type, order_type="MARKET", exchange_segment="NSE", product_type="INTRADAY"):
        url = f"{self.base_url}/orders"
        data = {
            "security_id": symbol,
            "quantity": quantity,
            "transaction_type": transaction_type,  # "BUY" or "SELL"
            "order_type": order_type,
            "exchange_segment": exchange_segment,
            "product_type": product_type,
            "client_id": self.client_id
        }
        response = requests.post(url, headers=self.headers, data=json.dumps(data))
        return response.json()

    def square_off_all_positions(self):
        url = f"{self.base_url}/squareoff"
        response = requests.post(url, headers=self.headers)
        return response.json()
