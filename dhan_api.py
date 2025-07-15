# Handles margin check, order placement via Dhan API

import requests
import json
from config import DHAN_API_KEY, DHAN_CLIENT_ID

BASE_URL = "https://api.dhan.co"

class DhanTrader:
    def __init__(self):
        self.api_key = DHAN_API_KEY
        self.client_id = DHAN_CLIENT_ID
        self.headers = {
            "Content-Type": "application/json",
            "access-token": self.api_key,
            "client-id": self.client_id
        }

    def place_order(self, order_data):
        url = f"{BASE_URL}/orders"
        response = requests.post(url, headers=self.headers, json=order_data)
        return response.json()

    def get_instrument_details(self, symbol):
        # Placeholder if you want to lookup token details etc.
        return {}

    def get_mtm(self):
        # Optional future enhancement
        return 0

    def get_margin_required(self, basket_data):
        url = f"{BASE_URL}/orders/margin-details"
        response = requests.post(url, headers=self.headers, json=basket_data)
        if response.status_code == 200:
            return response.json().get("totalMargin", 0)
        return None

    def exit_all_positions(self):
        url = f"{BASE_URL}/positions/intraday"
        response = requests.get(url, headers=self.headers)
        if response.status_code != 200:
            return []

        positions = response.json()
        exit_orders = []
        for position in positions:
            if position["quantity"] != 0:
                order_data = {
                    "transactionType": "SELL" if position["quantity"] > 0 else "BUY",
                    "quantity": abs(position["quantity"]),
                    "exchangeSegment": position["exchangeSegment"],
                    "productType": position["productType"],
                    "orderType": "MARKET",
                    "securityId": position["securityId"],
                    "tradingSymbol": position["tradingSymbol"],
                    "price": 0,
                    "disclosedQuantity": 0,
                    "validity": "DAY"
                }
                self.place_order(order_data)
                exit_orders.append(order_data)
        return exit_orders
