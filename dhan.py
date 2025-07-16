# dhan.py

import requests
import json

class Dhan:
    def __init__(self, auth_token):
        self.base_url = "https://api.dhan.co"
        self.auth_token = auth_token
        self.headers = {
            "accept": "application/json",
            "access-token": self.auth_token
        }

    def get_positions(self):
        url = f"{self.base_url}/positions"
        res = requests.get(url, headers=self.headers)
        return res.json() if res.status_code == 200 else []

    def get_orders(self):
        url = f"{self.base_url}/orders"
        res = requests.get(url, headers=self.headers)
        return res.json() if res.status_code == 200 else []

    def get_holdings(self):
        url = f"{self.base_url}/holdings"
        res = requests.get(url, headers=self.headers)
        return res.json() if res.status_code == 200 else []

    def get_fund_margin(self):
        url = f"{self.base_url}/margins/fund"
        res = requests.get(url, headers=self.headers)
        return res.json() if res.status_code == 200 else {}

    def place_order(self, data):
        url = f"{self.base_url}/orders"
        res = requests.post(url, json=data, headers=self.headers)
        try:
            return res.json()
        except Exception as e:
            print(f"[ERROR] Order placement failed: {res.text}")
            return {}

    def exit_order(self, order_id):
        url = f"{self.base_url}/orders/{order_id}"
        res = requests.delete(url, headers=self.headers)
        return res.status_code == 200
