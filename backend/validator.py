import os
import json
import time
import click
import threading
from flask import request
from web3 import Web3
import requests
from dotenv import load_dotenv, set_key
import sys

from chainsettle import network_func, SUPPORTED_NETWORKS, is_validator,load_last_block, load_or_create_validator_key, start_listener

# Load environment
load_dotenv()

SOLIDITY_ENV_PATH = os.path.join(os.getcwd(), 'solidity', '.env')
load_dotenv(dotenv_path=SOLIDITY_ENV_PATH, override=True)

global PRIVATE_KEY

ALCHEMY_API_KEY = os.getenv("ALCHEMY_API_KEY")
FAUCET_URL = os.getenv("FAUCET_URL")
LOCAL_URL = os.getenv('LOCAL_URL')

CONFIG_PATH = os.path.join(os.getcwd(), 'solidity','chainsettle_config.json')
with open(CONFIG_PATH, "r") as f:
    config = json.load(f)

print(F'[→] Config loaded from chainsettle_config.json')

# Verify the addresses (Optional debug prints)
for network, cfg in config.items():
    print(f"[{network.upper()}] Addresses Loaded:")
    for reg_name, address in cfg['registry_addresses'].items():
        print(f"  {reg_name}: {address}")

@click.group()
def cli():
    pass

@cli.command()
@click.option('--network', required=True, type=click.Choice(SUPPORTED_NETWORKS + ['all']))
@click.option('--new-wallet', is_flag=True, default=False, help='Create a new wallet and exit.')
@click.option('--account', default=None, type=str, help='Specify an account to use.')
def listen(network, new_wallet, account):
    """Listen for Attested events and auto-vote as validator."""

    private_key = None if new_wallet else os.getenv("VALIDATOR_NODE_KEY")
    if account:
        private_key = None  # force keystore lookup
    private_key = load_or_create_validator_key(private_key, new_wallet, account)
    if not private_key:
        print("[ERROR] Could not load or generate validator key.")
        sys.exit(1)

    networks = SUPPORTED_NETWORKS if network == "all" else [network]

    for net in networks:
        print(f"\n[INFO] --- Bootstrapping network: {net.upper()} ---")
        w3, account = network_func(network=net, ALCHEMY_API_KEY=ALCHEMY_API_KEY, PRIVATE_KEY=private_key)
        balance = w3.eth.get_balance(account.address)
        print(f"[INFO] Address: {account.address}")
        print(f"[INFO] Balance: {w3.from_wei(balance, 'ether')} ETH")

        VALIDATOR_REGISTRY_ADDRESS = Web3.to_checksum_address(config[net]['registry_addresses']['ValidatorRegistry'])
        abi_data = config[net]['abis']['ValidatorRegistry']

        # Register as validator if not already
        if new_wallet or not is_validator(w3, VALIDATOR_REGISTRY_ADDRESS, abi_data, account):
            print(f"[INFO] Validator not registered on {net}. Attempting registration...")
            api_key = os.getenv("VALIDATOR_API_KEY") or click.prompt("[INPUT] Enter your one-time API key", type=str)

            try:
                resp = requests.post(f'{LOCAL_URL}/add_validator', json={
                    'api_key': api_key,
                    'validator': account.address,
                    'network': net
                })
                resp.raise_for_status()
                print(f"[INFO] Successfully registered on {net}.")
            except Exception as e:
                print(f"[ERROR] Could not register validator on {net}: {e}")
                sys.exit(1)

        # Faucet call if balance is low
        if balance < Web3.to_wei(0.01, "ether"):
            print(f"[WARN] Low balance on {net}. Attempting faucet...")
            try:
                r = requests.post(FAUCET_URL, json={'address': account.address, 'network': net})
                r.raise_for_status()
                print(f"[INFO] Faucet responded: {r.json()}")
            except Exception as e:
                print(f"[WARN] Faucet failed on {net}: {e} (Continuing...)")

    # Start listeners after setup
    if network == 'all':
        threads = []
        for net in SUPPORTED_NETWORKS:
            t = threading.Thread(target=start_listener, args=(net, private_key, config, ALCHEMY_API_KEY), daemon=True)
            t.start()
            threads.append(t)
        try:
            while True:
                time.sleep(10)
        except KeyboardInterrupt:
            print("Shutting down validator node...")
    else:
        start_listener(network, private_key, config, ALCHEMY_API_KEY)

if __name__ == "__main__":
    print(f'[INFO] Starting Validator Node...')
    cli()