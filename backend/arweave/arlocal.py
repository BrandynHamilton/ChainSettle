import os
import arweave
import time
import requests
import click
from dotenv import load_dotenv, set_key

from chainsettle import (get_tx_status, post_to_arweave)

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
ENV_PATH = os.path.join(ROOT_DIR, '.env')
load_dotenv(dotenv_path=ENV_PATH)

arweave.api_config = {
    'host': 'localhost',
    'port': 1984,
    'protocol': 'http'
}

@click.group()
def cli():
    pass

@cli.command()
@click.option('--address', default=None, help="Address to fund (default: from arweave_keyfile.json)")
@click.option('--amount', default=1000, type=float, help="Amount to mint in AR (default: 1000)")
@click.option('--set-env', is_flag=True, help="Store the address in .env as ARWEAVE_ADDRESS")
def fund(address, amount, set_env):
    """Mint funds to an address."""
    if not address:
        wallet_file_path = 'arweave_keyfile.json'
        wallet = arweave.Wallet(wallet_file_path)
        address = wallet.address
        if set_env:
            set_key(ENV_PATH, 'ARWEAVE_ADDRESS', address)
        print(f'Using wallet: {address}')
    else:
        print(f'Funding external address: {address}')

    winston_amount = int(amount * 1e12)
    requests.get(f'http://localhost:1984/mint/{address}/{winston_amount}')
    requests.get('http://localhost:1984/mine')

    for i in range(5):
        res = requests.get(f'http://localhost:1984/wallet/{address}/balance')
        balance = int(res.text) / 1e12
        if balance > 0:
            break
        print(f'Balance still zero... retrying ({i+1}/5)')
        time.sleep(1)

    print(f'Wallet balance: {balance:.4f} AR')

@cli.command()
@click.option('--data', required=True, help="Data string to post to Arweave.")
def post_data(data):
    """Post simple text data to Arweave."""
    wallet_file_path = 'arweave_keyfile.json'
    wallet = arweave.Wallet(wallet_file_path)

    tx = post_to_arweave(wallet, data)
    print(f'Posted data to Arweave. Transaction ID: {tx.id}')

    status = requests.get(f"http://localhost:1984/tx/{tx.id}/status")
    print(f'Transaction status: {status}')

    print(f'Posted data to Arweave. Transaction ID: {tx.id}')

@cli.command()
@click.argument('tx_id')
def get_data(tx_id):
    """Retrieve and display data from Arweave using a transaction ID."""
    try:
        response = requests.get(f"http://localhost:1984/{tx_id}")
        if response.status_code == 200:
            print(f"Data for TXID {tx_id}:\n{response.text}")
        elif response.status_code == 202:
            print(f"Transaction {tx_id} is pending.")
        elif response.status_code == 404:
            print(f"Transaction {tx_id} not found.")
        else:
            print(f"Unexpected response ({response.status_code}): {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"An error occurred while fetching the data: {e}")

if __name__ == "__main__":
    cli()
