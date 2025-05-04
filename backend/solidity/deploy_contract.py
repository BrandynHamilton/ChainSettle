import os
import json
import time
import click
import datetime as dt

from dotenv import load_dotenv, set_key
from web3 import Web3
from solcx import compile_source, install_solc, set_solc_version

from chainsettle import network_func, deploy_contract

# Load environment variables
load_dotenv()

# def deploy_contract(
#     private_key, 
#     network,
#     contract_file, 
#     output_values=['abi', 'bin'], 
#     constructor_args=None,
#     solidity_version='0.8.19',
#     save_env_key_base=None,
#     save_env_path='.env'
# ):
#     if not contract_file.endswith('.sol'):
#         contract_file = contract_file + '.sol'

#     path = os.path.join('contracts', contract_file)

#     # Install compiler version
#     install_solc(solidity_version)
#     set_solc_version(solidity_version)

#     # Connect to network
#     w3, _ = network_func(network=network, ALCHEMY_API_KEY=os.getenv('ALCHEMY_API_KEY'), PRIVATE_KEY=private_key)

#     # Load account
#     account = w3.eth.account.from_key(private_key)

#     # Read and compile contract
#     with open(path, 'r', encoding='utf-8') as f:
#         solidity_code = f.read()

#     compiled_sol = compile_source(
#         solidity_code,
#         output_values=output_values
#     )

#     print("Compiled contracts:", compiled_sol.keys())

#     contract_file_name = contract_file.replace('.sol', '')

#     contract_key = next(
#         (key for key in compiled_sol.keys() if contract_file_name in key.split(":")[-1]),
#         None
#     )
#     if not contract_key:
#         raise Exception(f"Contract {contract_file_name} not found in compiled sources. Available keys: {list(compiled_sol.keys())}")

#     print(f"Using contract key: {contract_key}")
#     contract_interface = compiled_sol[contract_key]
#     contract_abi = contract_interface['abi']
#     bytecode = contract_interface['bin']

#     contract_obj = w3.eth.contract(abi=contract_abi, bytecode=bytecode)

#     estimated_gas = contract_obj.constructor(**(constructor_args or {})).estimate_gas({
#         "from": account.address
#     })

#     latest_block = w3.eth.get_block("latest")
#     base_fee = latest_block.get("baseFeePerGas", w3.to_wei(1, "gwei"))
#     max_priority_fee = w3.to_wei("2", "gwei")
#     max_fee = base_fee + max_priority_fee * 2

#     tx = contract_obj.constructor(**(constructor_args or {})).build_transaction({
#         "from": account.address,
#         "nonce": w3.eth.get_transaction_count(account.address),
#         "gas": int(estimated_gas * 1.2),
#         "maxFeePerGas": max_fee,
#         "maxPriorityFeePerGas": max_priority_fee,
#         "type": 2,
#     })

#     estimated_cost = int(estimated_gas * 1.2) * max_fee
#     native_balance = w3.eth.get_balance(account.address)

#     if native_balance < estimated_cost:
#         raise Exception(
#             f"Insufficient native gas token balance on {network}. "
#             f"Have: {w3.from_wei(native_balance, 'ether')} - Need: {w3.from_wei(estimated_cost, 'ether')}"
#         )

#     signed_tx = w3.eth.account.sign_transaction(tx, private_key=private_key)
#     tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

#     print(f"Sent transaction: {tx_hash.hex()}")

#     receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

#     if receipt.status == 1:
#         contract_address = receipt.contractAddress
#         print(f"Contract deployed successfully at: {contract_address}")

#         # Save ABI (optional)
#         abi_file_path = os.path.join('abi', f"{contract_file.replace('.sol','')}_{network.upper()}_abi.json")
#         os.makedirs(os.path.dirname(abi_file_path), exist_ok=True)
#         with open(abi_file_path, 'w') as f:
#             json.dump(contract_abi, f, indent=2)
#         print(f"ABI saved at {abi_file_path}")

#         # Save to env file if requested
#         if save_env_key_base:
#             save_key_name = f"{save_env_key_base.upper()}_{network.upper()}"
#             set_key(dotenv_path=save_env_path, key_to_set=save_key_name, value_to_set=contract_address)
#             print(f"Environment variable '{save_key_name}' updated in {save_env_path}")

#         return contract_address
#     else:
#         raise Exception(f"Contract deployment failed. Receipt: {receipt}")

@click.command()
@click.option('--contract', required=True, help="Name of the Solidity contract (inside /contracts)")
@click.option('--network', required=True, type=click.Choice(['ethereum', 'blockdag']), help="Target network")
@click.option('--save-env-key-base', required=False, help="Environment variable key to save deployed address to")
@click.option('--constructor-args', required=False, default="{}", help="Constructor args as JSON dict (optional)")
@click.option('--config-keyword', required=False, default=None, type=str, help="Config keyword to save deployed address and abi to")
def main(contract, network, save_env_key_base, constructor_args, config_keyword):
    """
    Deploy a smart contract and optionally save the deployed address to .env
    """
    ALCHEMY_API_KEY = os.getenv('ALCHEMY_API_KEY')
    PRIVATE_KEY = os.getenv('FAUCET_PRIVATE_KEY')

    if not ALCHEMY_API_KEY or not PRIVATE_KEY:
        raise Exception("Missing ALCHEMY_API_KEY or EVM_PRIVATE_KEY in environment.")

    # Parse constructor args if provided
    if os.path.isfile(constructor_args):
        with open(constructor_args, 'r') as f:
            constructor_args_dict = json.load(f)
    else:
        constructor_args_dict = json.loads(constructor_args)

    contract_address, contract_abi_file_path = deploy_contract(
        private_key=PRIVATE_KEY,
        network=network,
        contract_file=contract,
        constructor_args=constructor_args_dict,
        save_env_key_base=save_env_key_base
    )

    if config_keyword is not None:

        CONFIG_PATH = os.path.join(os.getcwd(), 'chainsettle_config.json')
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)

        if config_keyword not in config[network]:
            config[network][config_keyword] = {}

        config[network][config_keyword]['addresses'] = contract_address
        config[network][config_keyword]['abis'] = json.load(open(contract_abi_file_path))

        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)
        
if __name__ == "__main__":
    main()
