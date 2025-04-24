import requests
import time
import os 
import datetime as dt
from datetime import timedelta
import time
from dotenv import load_dotenv, set_key
import json

import plaid
from plaid.api import plaid_api
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.sandbox_public_token_create_request import SandboxPublicTokenCreateRequest
from plaid.model.sandbox_public_token_create_request_options import SandboxPublicTokenCreateRequestOptions
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.products import Products
from plaid.model.country_code import CountryCode

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

def generate_custom_sandbox_tx(amount, escrow_id, date=None):
    if not date:
        date = dt.date.today().isoformat()

    # Optional: simulate 1-day lag between transaction and posting
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
                        "description": f"Escrow {escrow_id} payment",
                        "currency": "USD"
                    }
                ]
            }
        ]
    }

def simulate_plaid_tx_and_get_access_token(client, amount, escrow_id):
    url = "https://sandbox.plaid.com/sandbox/public_token/create"

    config_dict = generate_custom_sandbox_tx(amount, escrow_id)
    config_str = json.dumps(config_dict)  # Still needs to be stringified

    print(f'config: {config_str}')

    print("client_id:", PLAID_CLIENT_ID)
    print("secret:", PLAID_SANDBOX_KEY)

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

    print("Sending payload to Plaid sandbox:", json.dumps(payload, indent=2))

    res = requests.post(url, json=payload)

    print(f'res: {res}')

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

#Github attestation helper functions
def github_tag_exists(owner: str, repo: str, tag: str) -> bool:
    url = f"https://api.github.com/repos/{owner}/{repo}/tags"
    headers = {"Accept": "application/vnd.github+json"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        tags = [t["name"] for t in response.json()]
        return tag in tags
    return False

def github_file_exists(owner: str, repo: str, path: str, branch="main") -> bool:
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={branch}"
    response = requests.get(url)
    return response.status_code == 200

def parse_date(value, fallback):
    if isinstance(value, str):
        return dt.datetime.fromisoformat(value).date()
    elif isinstance(value, dt.date):
        return value
    else:
        return fallback
