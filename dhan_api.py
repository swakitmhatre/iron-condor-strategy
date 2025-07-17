# dhan_api.py

import requests
from config import DHAN_BASE_URL, DHAN_API_TOKEN
from utils import log_message

class DhanTrader:
    def __init__(self):
        self.base_url = DHAN_BASE_URL
        self.headers = {
            "accept": "application/json",
            "access-token": DHAN_API_TOKEN
        }

    def get_nifty_spot(self):
        """
        Fetch NIFTY 50 live LTP using marketfeed/ltp endpoint.
        Security ID 13 is used for NIFTY 50.
        """
        SECURITY_ID = 13
        url = f"{self.base_url}/v2/marketfeed/ltp"
        payload = {
            "NSE_IDX": [SECURITY_ID],
            "NSE_FNO": []
        }

        try:
            response = requests.post(url, json=payload, headers=self.headers)
            data = response.json()
            log_message(f"NIFTY LTP API response: {data}")

            if response.status_code == 200 and "data" in data:
                if "NSE_IDX" in data["data"]:
                    index_data = data["data"]["NSE_IDX"]
                    if str(SECURITY_ID) in index_data:
                        return index_data[str(SECURITY_ID)]["last_price"]
            raise ValueError(f"Fetch NIFTY spot failed: {data}")
        except Exception as e:
            raise ValueError(f"Fetch spot failed: {str(e)}")
