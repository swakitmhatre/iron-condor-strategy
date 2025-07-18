# dhan.py
import requests

class Dhan:
    def __init__(self, access_token: str, client_id: str):
        self.access_token = access_token
        self.client_id = client_id
        self.base = "https://api.dhan.co/v2"

    def get_nifty_spot(self) -> float:
        url = f"{self.base}/marketfeed/ltp"
        hdrs = {
            "Content-Type": "application/json",
            "access-token": self.access_token,
            "client-id": self.client_id,
        }
        data = {"IDX_I": [13]}
        resp = requests.post(url, json=data, headers=hdrs)
        result = resp.json()
        if resp.status_code == 200 and result.get("status") == "success":
            return float(result["data"]["IDX_I"]["13"]["last_price"])
        raise ValueError(f"Fetch NIFTY spot failed: {result}")
