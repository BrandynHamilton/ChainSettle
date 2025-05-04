import plaid
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions
from plaid.api import plaid_api
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.sandbox_public_token_create_request import SandboxPublicTokenCreateRequest
from plaid.model.sandbox_public_token_create_request_options import SandboxPublicTokenCreateRequestOptions
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.products import Products
from plaid.model.country_code import CountryCode

import requests
import time
import os
import json
from dotenv import load_dotenv, set_key
import datetime as dt
from datetime import timedelta

load_dotenv()

CLIENT_NAME='ChainSettle'
PLAID_CLIENT_ID = os.getenv('PLAID_CLIENT_ID')
PLAID_SANDBOX_KEY = os.getenv('PLAID_SANDBOX_KEY')

assert PLAID_CLIENT_ID and PLAID_SANDBOX_KEY, "Missing Plaid credentials"

def create_plaid_client():
    configuration = plaid.Configuration(
        host=plaid.Environment.Sandbox,
        api_key={
            'clientId': PLAID_CLIENT_ID,
            'secret': PLAID_SANDBOX_KEY
        }
    )

    client = None

    try:
        api_client = plaid.ApiClient(configuration)
        client = plaid_api.PlaidApi(api_client)
    except Exception as e:
        print(f'e: {e}')

    return client

def create_link_token():

    client = create_plaid_client()

    response = None

    try:
        request = LinkTokenCreateRequest(
            products=[Products("auth"), Products("transactions")],
            client_name=CLIENT_NAME,
            country_codes=[CountryCode("US")],
            language="en",
            user=LinkTokenCreateRequestUser(client_user_id=str(time.time())),
        )
        response = client.link_token_create(request)
    except Exception as e:
        print(f'e: {e}')

    if response:
        link_token = response['link_token']
    else:
        link_token = None

    return link_token

def generate_custom_sandbox_tx(amount, settlement_id, date=None):
    if not date:
        date = dt.date.today().isoformat()

    # Simulate 1-day lag between transaction and posting
    date_posted = dt.datetime.fromisoformat(date) + timedelta(days=1)
    date_posted = date_posted.date().isoformat()

    return {
        "override_accounts": [
            {
                "type": "depository",
                "subtype": "checking",
                "transactions": [
                    {
                        "date_transacted": date,
                        "date_posted": date_posted,
                        "amount": amount,
                        "description": f"settlement {settlement_id} payment",
                        "currency": "USD"
                    }
                ]
            }
        ]
    }

def simulate_plaid_tx_and_get_access_token(client, amount, settlement_id):
    url = "https://sandbox.plaid.com/sandbox/public_token/create"

    config_dict = generate_custom_sandbox_tx(amount, settlement_id)
    config_str = json.dumps(config_dict) 

    payload = {
        "client_id": PLAID_CLIENT_ID,
        "secret": PLAID_SANDBOX_KEY,
        "institution_id": "ins_109508",
        "initial_products": ["transactions"],
        "options": {
            "override_username": "user_custom",
            "override_password": config_str,
        }
    }

    res = requests.post(url, json=payload)

    if not res.ok:
        print("Plaid error response:")
        try:
            print(json.dumps(res.json(), indent=2))
        except:
            print(res.text)
        res.raise_for_status()

    public_token = res.json()["public_token"]
    exchange_request = ItemPublicTokenExchangeRequest(public_token=public_token)
    exchange_response = client.item_public_token_exchange(exchange_request)
    return exchange_response["access_token"]

def wait_for_transaction_settlement(plaid_client, access_token, settlement_id, amount, 
                                    start_date, end_date, max_retries=2, poll_interval=15):

    tx_request = TransactionsGetRequest(
        access_token=access_token,
        start_date=start_date,
        end_date=end_date,
        options=TransactionsGetRequestOptions()
    )

    time.sleep(5)

    attempt = 0
    while attempt < max_retries:
        try:
            plaid_response = plaid_client.transactions_get(tx_request)
            transactions = plaid_response["transactions"]
        except Exception as e:
            print(f"Error fetching transactions: {e}")
            transactions = []

        for tx in transactions:
            tx_amt = float(tx.get("amount", 0))
            tx_name = tx.get("name", "")
            pending = tx.get("pending", False)

            if abs(tx_amt - float(amount)) < 0.01 and settlement_id.lower() in tx_name.lower():
                print(f"Found transaction: {tx_name} for amount {tx_amt} (pending: {pending})\n{tx}")
                if not pending:
                    print(f"Settled transaction found at attempt {attempt}")
                    return tx
                else:
                    print(f"Matching transaction is still pending (attempt {attempt})")

        attempt += 1
        time.sleep(poll_interval)

    print(f"Max retries reached. No settled transaction found.")
    return 