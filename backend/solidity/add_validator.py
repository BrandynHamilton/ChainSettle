import os
import json
import time
import click
import datetime as dt

from dotenv import load_dotenv, set_key
from pydantic import validator
from web3 import Web3
from solcx import compile_source, install_solc, set_solc_version

from chainsettle import network_func, add_validator, get_validator_list, SUPPORTED_NETWORKS

@click.command()
@click.option('--new_validator_address', required=False, help="Address to add as a validator")
@click.option('--list_validators', is_flag=True, default=False, help="List validators on the network")
@click.option('--network', required=True, type=click.Choice(SUPPORTED_NETWORKS + ['all']))
def main(new_validator_address, list_validators, network):
    load_dotenv()

    # VALIDATOR_REGISTRY_ADDRESS_ETHEREUM = os.getenv('VALIDATOR_REGISTRY_ADDRESS_ETHEREUM')
    # VALIDATOR_REGISTRY_ADDRESS_BLOCKDAG = os.getenv('VALIDATOR_REGISTRY_ADDRESS_BLOCKDAG')

    # VALIDATOR_ABI_PATH_ETHEREUM = os.path.join('abi', 'ValidatorRegistry_ETHEREUM_abi.json')
    # VALIDATOR_ABI_PATH_BLOCKDAG = os.path.join('abi', 'ValidatorRegistry_BLOCKDAG_abi.json')

    # address_map = {
    #     'ethereum': VALIDATOR_REGISTRY_ADDRESS_ETHEREUM,
    #     'blockdag': VALIDATOR_REGISTRY_ADDRESS_BLOCKDAG
    # }

    # abi_map = {
    #     'ethereum': VALIDATOR_ABI_PATH_ETHEREUM,
    #     'blockdag': VALIDATOR_ABI_PATH_BLOCKDAG
    # }

    CONFIG_PATH = os.path.join(os.getcwd(), 'chainsettle_config.json')
    with open(CONFIG_PATH, "r") as f:
        config = json.load(f)

    ALCHEMY_API_KEY = os.getenv('ALCHEMY_API_KEY')
    PRIVATE_KEY = os.getenv('EVM_PRIVATE_KEY')

    if not ALCHEMY_API_KEY or not PRIVATE_KEY:
        raise Exception("Missing ALCHEMY_API_KEY or EVM_PRIVATE_KEY in environment.")

    target_networks = SUPPORTED_NETWORKS if network == 'all' else [network]

    for net in target_networks:
        print(f"\n--- [{net.upper()}] ---")

        if list_validators:
            print("Listing validators...")
            owner, validator_count, validator_registry = get_validator_list(
                private_key=PRIVATE_KEY,
                network=net,
                config=config
            )
            print(f"Owner: {owner}")
            print(f"Validator Count: {validator_count}")
            print("Validator Registry:")
            for v in validator_registry:
                print(f"- {v}")
        elif new_validator_address:
            # Check if already added
            _, _, validator_registry = get_validator_list(
                private_key=PRIVATE_KEY,
                network=net,
                config=config
            )
            if Web3.to_checksum_address(new_validator_address) in validator_registry:
                print(f"[{net.upper()}] Already registered, skipping: {new_validator_address}")
                continue

            print(f"Adding new validator: {new_validator_address}")
            print(f"Checksum address: {new_validator_address}")
            add_validator(
                private_key=PRIVATE_KEY,
                network=net,
                new_validator_address=new_validator_address,
                config=config
            )
        else:
            print(f"[{net.upper()}] No action taken. Use --list_validators or --new_validator_address.")

if __name__ == "__main__":
    main()
