import os
import json
import time
import click
import datetime as dt
import threading

from dotenv import load_dotenv, set_key
from web3 import Web3
from solcx import compile_source, install_solc, set_solc_version
from getpass import getpass

from chainsettle import (network_func, deploy_contract, SUPPORTED_NETWORKS, add_validator, encrypt_keystore, 
                         BLOCK_EXPLORER_MAP, create_wallet, start_listener, get_validator_list)

# Load environment variables
load_dotenv()

@click.command()
@click.option('--nodes', required=False, default=0, help="Number of validator nodes to deploy (default: 0)")
@click.option('--only-validators', is_flag=True, help="Only start validators (no contract deployment)")
@click.option('--allowlist', default=None, type=click.Path(exists=True), help="CSV file of validator addresses to allowlist")
def main(nodes, only_validators, allowlist):
    ALCHEMY_API_KEY = os.getenv('ALCHEMY_API_KEY')
    PRIVATE_KEY = os.getenv('EVM_PRIVATE_KEY')
    if not ALCHEMY_API_KEY or not PRIVATE_KEY:
        raise Exception("Missing ALCHEMY_API_KEY or EVM_PRIVATE_KEY in environment.")

    validator_wallets = []

    # STEP 1 — Generate wallets once (shared across all networks)
    for i in range(nodes):
        priv_key, address = create_wallet()
        print(f"Generated wallet {i+1}: {address}")
        password = getpass("Enter password to encrypt keystore: ")
        encrypt_keystore(priv_key, password)
        validator_wallets.append((address, priv_key))

    config = {}

    # STEP 2 — Loop through each network and deploy, register, listen
    for network in SUPPORTED_NETWORKS:

        w3, account = network_func(network=network, ALCHEMY_API_KEY=ALCHEMY_API_KEY, PRIVATE_KEY=PRIVATE_KEY)

        print(F'[→] Network: {network}')
        print(f"Account: {account.address}")

        upper = network.upper()

        if not only_validators:
            print(f"Deploying contracts on {network}...")
            validator_contract_address, validator_abi_file_path = deploy_contract(private_key=PRIVATE_KEY, network=network, contract_file="ValidatorRegistry.sol", save_env_key_base="VALIDATOR_REGISTRY_ADDRESS")
            time.sleep(3)

            # validator_address = os.getenv(f'VALIDATOR_REGISTRY_ADDRESS_{upper}')
            settlement_contract_address, settlement_abi_file_path = deploy_contract(
                private_key=PRIVATE_KEY,
                network=network,
                contract_file="SettlementRegistry.sol",
                constructor_args={'_validatorRegistry': validator_contract_address},
                save_env_key_base="SETTLEMENT_REGISTRY_ADDRESS"
            )
            time.sleep(3)
        else:
            print(f"Skipping contract deployment on {network}...")

        config[network] = {
            'explorer_url': BLOCK_EXPLORER_MAP.get(network),
            'registry_addresses': {
                'SettlementRegistry': settlement_contract_address,
                'ValidatorRegistry': validator_contract_address,
            },
            'abis': {
                'SettlementRegistry': json.load(open(settlement_abi_file_path)),
                'ValidatorRegistry': json.load(open(validator_abi_file_path))
            }
        }

        w3, account = network_func(network=network, ALCHEMY_API_KEY=ALCHEMY_API_KEY, PRIVATE_KEY=PRIVATE_KEY)

        deployer_address = Web3.to_checksum_address(account.address)

        owner, validator_count, validator_registry = get_validator_list(
            private_key=PRIVATE_KEY,
            network=network,
            config=config
        )

        if deployer_address not in validator_registry:
            print(f"Adding deployer {deployer_address} as validator on {network}...")
            add_validator(
                private_key=PRIVATE_KEY,
                network=network,
                new_validator_address=deployer_address,
                config=config
            )
            print(f"[✓] Deployer added to {network}")
        else:
            print(f"[→] Deployer {deployer_address} already registered on {network}")


        # Register allowlist if provided
        if allowlist:
            with open(allowlist, 'r') as f:
                for line in f:
                    addr = line.strip()
                    if addr:
                        add_validator(
                            private_key=PRIVATE_KEY,
                            network=network,
                            new_validator_address=addr,
                            config=config
                        )
                        print(f"Allowlisted validator {addr} on {network}")
                        time.sleep(1)

        # Register all generated wallets on this network
        for address, priv_key in validator_wallets:
            add_validator(
                private_key=PRIVATE_KEY,
                network=network,
                new_validator_address=address,
                config=config
            )
            print(f"Validator {address} added to {network}")
            time.sleep(1)

        # Start listeners for each validator on this network
        for i, (address, priv_key) in enumerate(validator_wallets):
            thread_name = f"{network}-validator-{i}"
            print(f"[→] Starting listener: {thread_name} for wallet {address}")
            threading.Thread(
                target=start_listener,
                args=(network, priv_key, config, ALCHEMY_API_KEY),
                daemon=True,
                name=thread_name
            ).start()
    
    # After the for network in SUPPORTED_NETWORKS loop
    with open("chainsettle_config.json", "w") as f:
        json.dump(config, f, indent=2)

    print("[✓] Config saved to chainsettle_config.json")

    if nodes > 0:
        print(f"[✓] {len(nodes)} validator wallets generated and registered.")
        try:
            while True:
                time.sleep(10)
        except KeyboardInterrupt:
            print("\n[!] Shutting down validators...")

if __name__ == "__main__":
    main()
