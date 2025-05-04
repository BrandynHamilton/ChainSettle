# chainsettle/paypal.py

import os
import time
import requests
from requests.auth import HTTPBasicAuth
import logging
import json

from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

LOCAL_URL = os.getenv("LOCAL_URL", "http://localhost:5045")  # Default to localhost if not set

def find_settlement_id_by_order(order_id, SETTLEMENT_STORE_PATH):
    print(f'os.listdir(SETTLEMENT_STORE_PATH): {os.listdir(SETTLEMENT_STORE_PATH)}')
    for file in os.listdir(SETTLEMENT_STORE_PATH):
        path = os.path.join(SETTLEMENT_STORE_PATH, file)
        if not path.endswith(".json"):
            continue
        with open(path, "r") as f:
            data = json.load(f)
            if data.get("order_id") == order_id:
                print(f'matched data: {data}')
                return data.get("settlement_id")
    return None

class PayPalModule:
    def __init__(self, sandbox=True):
        self.client_id = os.getenv("PAYPAL_CLIENT_ID")
        self.client_secret = os.getenv("PAYPAL_CLIENT_SECRET")
        if not self.client_id or not self.client_secret:
            raise RuntimeError("Missing PayPal credentials in environment variables")

        self.api_base = "https://api-m.sandbox.paypal.com" if sandbox else "https://api-m.paypal.com"
        self.access_token = self._get_access_token()

        self.logger = logging.getLogger("ChainSettlePayPal")
        logging.basicConfig(level=logging.INFO)

    def _get_access_token(self):
        res = requests.post(
            f"{self.api_base}/v1/oauth2/token",
            headers={"Accept": "application/json", "Accept-Language": "en_US"},
            data={"grant_type": "client_credentials"},
            auth=HTTPBasicAuth(self.client_id, self.client_secret)
        )
        res.raise_for_status()
        return res.json()["access_token"]

    def create_order(self, recipient_email: str, amount: float, currency="USD", metadata=None):
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.access_token}"
        }

        amount_str = f"{amount:.2f}"
        order_data = {
            "intent": "CAPTURE",
            "purchase_units": [{
                "amount": {
                    "currency_code": currency,
                    "value": amount_str
                },
                "custom_id": metadata[:127] if metadata else None,
                "description": metadata[:127] if metadata else None
            }],
            "application_context": {
                "return_url": f"{LOCAL_URL}/paypal-success",
                "cancel_url": f"{LOCAL_URL}/paypal-cancel"
            }
        }

        res = requests.post(f"{self.api_base}/v2/checkout/orders", json=order_data, headers=headers)
        res.raise_for_status()
        order = res.json()
        approval_url = next(link['href'] for link in order['links'] if link['rel'] == 'approve')
        order_id = order['id']
        return order_id, approval_url

    def poll_for_approval(self, order_id: str, timeout=300, interval=5):
        headers = {"Authorization": f"Bearer {self.access_token}"}
        elapsed = 0
        while elapsed < timeout:
            res = requests.get(f"{self.api_base}/v2/checkout/orders/{order_id}", headers=headers)
            res.raise_for_status()
            status = res.json().get("status")
            self.logger.info(f"[PayPal] Order {order_id} status = {status}")
            if status == "APPROVED":
                return True
            time.sleep(interval)
            elapsed += interval
        return False

    def capture_order(self, order_id: str):
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.access_token}"
        }
        res = requests.post(f"{self.api_base}/v2/checkout/orders/{order_id}/capture", headers=headers)
        res.raise_for_status()
        return res.json()

    def wait_for_transaction_settlement(self, capture_id: str, timeout=60, interval=5):
        headers = {"Authorization": f"Bearer {self.access_token}"}
        elapsed = 0
        while elapsed < timeout:
            res = requests.get(f"{self.api_base}/v2/payments/captures/{capture_id}", headers=headers)
            res.raise_for_status()
            status = res.json().get("status")
            self.logger.info(f"[PayPal] Capture {capture_id} status = {status}")
            if status == "COMPLETED":
                return True
            time.sleep(interval)
            elapsed += interval
        return False
