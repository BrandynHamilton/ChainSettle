from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from web3.types import TxParams
from arweave import Transaction, Wallet
import time
from solcx import compile_source, install_solc, set_solc_version
import json
import requests
from dotenv import load_dotenv, set_key
import os
import random
from web3.exceptions import TimeExhausted

from requests.exceptions import ConnectionError as RequestsConnectionError
from requests import exceptions as req_ex

from chainsettle.wallet import generate_wallet 
from chainsettle.metadata import SUPPORTED_NETWORKS

def network_func(PRIVATE_KEY, network='ethereum',ALCHEMY_API_KEY=None):
    if network not in SUPPORTED_NETWORKS:
        raise Exception(f"Network {network} not supported. Supported networks are: {SUPPORTED_NETWORKS}")
    
    # Compose Gateway URLs
    if network == 'ethereum':
        if ALCHEMY_API_KEY is None:
            GATEWAY = 'https://eth-sepolia.public.blastapi.io'
        else:
            try:
                GATEWAY = f"https://eth-sepolia.g.alchemy.com/v2/{ALCHEMY_API_KEY}"
            except Exception as e:
                print(f"Failed to connect to Alchemy (Ethereum): {e}")
                GATEWAY = 'https://eth-sepolia.public.blastapi.io'

    elif network == 'base':
        if ALCHEMY_API_KEY is None:
            GATEWAY = 'https://base-sepolia.public.blastapi.io'
        else:
            try:
                GATEWAY = f"https://base-sepolia.g.alchemy.com/v2/{ALCHEMY_API_KEY}"
            except Exception as e:
                print(f"Failed to connect to Alchemy (Base): {e}")
                GATEWAY = 'https://base-sepolia.public.blastapi.io'

    elif network == 'blockdag':
        GATEWAY = 'https://rpc.primordial.bdagscan.com/'

    w3 = Web3(Web3.HTTPProvider(GATEWAY))

    account = None

    if w3.is_connected():
        try:
            account = w3.eth.account.from_key(PRIVATE_KEY)
            try:
                latest_block = w3.eth.get_block('latest')['number']
            except:
                latest_block = None
            print(f"Connected to {network} with account {account} - Block {latest_block}")
            return w3, account
        except Exception as e:
            print(f"Connected but failed to fetch block. Error: {e}")
            return w3, account
    else:
        print(f"Failed to connect to {network}")

def init_attest_onchain(w3, account, REGISTRY_ADDRESS, REGISTRY_ABI, settlement_type, amount, settlement_id, details = ""):

    settlement_registry_obj = w3.eth.contract(address=REGISTRY_ADDRESS, abi=REGISTRY_ABI)

    # === Parameters for attest function ===
    amount_scaled = int(amount * 1e6) # assuming usd/usdc parity

    # === Build the base tx without gas, to estimate ===
    base_tx = settlement_registry_obj.functions.initAttest(
        settlement_id,
        settlement_type,
        details,
        amount_scaled
    ).build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
    })

    # === Estimate Gas ===
    gas_estimate = w3.eth.estimate_gas(base_tx) 

    # === EIP-1559 Fee Data ===
    latest_block = w3.eth.get_block("latest")
    base_fee = latest_block.get("baseFeePerGas", w3.to_wei(15, "gwei"))
    priority_fee = w3.to_wei(2, "gwei")
    max_fee = base_fee + priority_fee

    # === Final EIP-1559 transaction ===
    tx: TxParams = {
        "from": account.address,
        "to": REGISTRY_ADDRESS,
        "nonce": base_tx["nonce"],
        "data": base_tx["data"],
        "gas": int(gas_estimate * 1.2),  # 20% buffer
        "maxPriorityFeePerGas": priority_fee,
        "maxFeePerGas": max_fee,
        "chainId": w3.eth.chain_id,
        "type": 2
    }

    # === Sign + Send ===
    signed_tx = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    print(f"Sent tx: {'0x'+receipt.transactionHash.hex()}")

    return receipt

def attest_onchain(w3, account, REGISTRY_ADDRESS, REGISTRY_ABI, amount, settlement_type, settlement_id, status_enum, details = ""):

    print(f'Attesting settlement {settlement_id} with amount {amount} and type {settlement_type}')

    settlement_registry_obj = w3.eth.contract(address=REGISTRY_ADDRESS, abi=REGISTRY_ABI)

    print(f'status_enum:{status_enum}')

    # === Parameters for attest function ===
    amount_scaled = int(amount * 1e6)

    nonce = w3.eth.get_transaction_count(account.address, 'pending')

    # === Build the base tx without gas, to estimate ===
    base_tx = settlement_registry_obj.functions.attest(
        settlement_id,
        settlement_type,
        status_enum,
        details,
        amount_scaled
    ).build_transaction({
        "from": account.address,
        "nonce": nonce,
    })

    # === Estimate Gas ===
    gas_estimate = w3.eth.estimate_gas(base_tx) 

    # === EIP-1559 Fee Data ===
    latest_block = w3.eth.get_block("latest")
    base_fee = latest_block.get("baseFeePerGas", w3.to_wei(15, "gwei"))
    priority_fee = w3.to_wei(2, "gwei")
    max_fee = base_fee + priority_fee

    # === Final EIP-1559 transaction ===
    tx: TxParams = {
        "from": account.address,
        "to": REGISTRY_ADDRESS,
        "nonce": base_tx["nonce"],
        "data": base_tx["data"],
        "gas": int(gas_estimate * 1.2),  # 20% buffer
        "maxPriorityFeePerGas": priority_fee,
        "maxFeePerGas": max_fee,
        "chainId": w3.eth.chain_id,
        "type": 2
    }

    # === Sign + Send ===
    signed_tx = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    attestation_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    print(f"Sent attestation tx: {'0x'+attestation_receipt.transactionHash.hex()}")

    time.sleep(1)
    # === Build the base tx for validation ===

    agree = True # We assume the validator agrees with the attestation, placeholder for now

    validation_tx = settlement_registry_obj.functions.voteOnSettlement(settlement_id,agree).build_transaction({
        "from": account.address,
        "nonce": nonce + 1,
    })

    validator_gas_estimate = w3.eth.estimate_gas(validation_tx) 

    validation_tx['gas'] = int(validator_gas_estimate * 1.2)  # 20% buffer
    validation_tx['maxPriorityFeePerGas'] = priority_fee
    validation_tx['maxFeePerGas'] = max_fee

    signed_tx = account.sign_transaction(validation_tx)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    validation_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    print(f"Sent validation tx: {'0x'+validation_receipt.transactionHash.hex()}")

    return {'attestation_receipt': attestation_receipt, 'validation_receipt': validation_receipt}

def get_last_tx():
    response = requests.get("http://localhost:1984/tx_anchor")
    if response.status_code == 200:
        return response.text
    else:
        raise Exception("Failed to fetch tx_anchor")

def post_to_arweave(wallet, data, settlement_id, mine=True, retries=10, delay=1):
    ARLOCAL_SERVER = os.getenv("ARLOCAL_SERVER", "http://localhost:1984")

    try:
        last_tx = get_last_tx()
        print(F'last_tx: {last_tx}')
        tx = Transaction(wallet, data=data)
        tx.add_tag("settlement_id", settlement_id)
        print(f'tx: {tx}')
        tx.last_tx = last_tx
        tx.sign()
        tx_data = tx.to_dict()

        response = requests.post(f"{ARLOCAL_SERVER}/tx", json=tx_data)
        if response.status_code != 200:
            print("Failed to post transaction")
            print(response.text)
            return None

        print(f"Posted transaction {tx.id}")

        if mine:
            mine_response = requests.get(f"{ARLOCAL_SERVER}/mine")
            if mine_response.status_code == 200:
                print("Block mined")

        for i in range(retries):
            status_response = requests.get(f"{ARLOCAL_SERVER}/tx/{tx.id}/status")
            if status_response.status_code == 200:
                print(f"Transaction confirmed: {tx.id}")
                return tx
            print(f"Waiting for confirmation... ({i+1}/{retries})")
            time.sleep(delay)

        print(f"Transaction not confirmed after {retries} retries: {tx.id}")
        return tx
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

def get_tx_status(tx_id):
    url = f"http://localhost:1984/tx/{tx_id}/status"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()  # Should return {"block_height": ..., "block_indep_hash": ..., "status": 200, ...}
    elif response.status_code == 202:
        return {"status": 202, "message": "Pending"}
    else:
        return {"status": response.status_code, "message": response.text}

def get_validator_list(
    private_key, 
    network,
    config
):
    # Connect to network
    w3, _ = network_func(network=network, ALCHEMY_API_KEY=os.getenv('ALCHEMY_API_KEY'), PRIVATE_KEY=private_key)

    VALIDATOR_REGISTRY_ADDRESS = config[network]['registry_addresses']['ValidatorRegistry']
    VALIDATOR_ABI = config[network]['abis']['ValidatorRegistry']

    # with open(VALIDATOR_ABI, 'r') as f:
    #     abi_data = json.load(f)

    # Load account
    account = w3.eth.account.from_key(private_key)

    contract_obj = w3.eth.contract(address=VALIDATOR_REGISTRY_ADDRESS,abi=VALIDATOR_ABI)

    owner = contract_obj.functions.owner().call()
    validator_count = contract_obj.functions.getValidatorCount().call()
    validator_registry = contract_obj.functions.getValidators().call()

    return owner, validator_count, validator_registry

def add_validator(
    private_key, 
    network,
    config,
    new_validator_address=None
):
    # Connect to network
    w3, _ = network_func(network=network, ALCHEMY_API_KEY=os.getenv('ALCHEMY_API_KEY'), PRIVATE_KEY=private_key)

    VALIDATOR_REGISTRY_ADDRESS = config[network]['registry_addresses']['ValidatorRegistry']
    VALIDATOR_ABI = config[network]['abis']['ValidatorRegistry']

    # with open(VALIDATOR_ABI, 'r') as f:
    #     abi_data = json.load(f)

    # Load account
    account = w3.eth.account.from_key(private_key)

    contract_obj = w3.eth.contract(address=VALIDATOR_REGISTRY_ADDRESS,abi=VALIDATOR_ABI)

    owner = contract_obj.functions.owner().call()
    validator_count = contract_obj.functions.getValidatorCount().call()
    validator_registry = contract_obj.functions.getValidators().call()

    if account.address != owner:
        raise Exception(f"Account {account.address} is not the owner of the contract {VALIDATOR_REGISTRY_ADDRESS}.")

    print(F'validator_count: {validator_count}')
    print(F'validator_registry: {validator_registry}')

    if new_validator_address is None:
        new_validator_address = owner

    if new_validator_address:
        if new_validator_address in validator_registry:
            raise Exception(f"Validator {new_validator_address} is already registered.")
        else:
            print(f"Adding new validator: {new_validator_address}")

            new_validator_address_checksum = w3.to_checksum_address(new_validator_address)
            print(f"Checksum address: {new_validator_address_checksum}")

            estimated_gas = contract_obj.functions.registerValidator(new_validator_address_checksum).estimate_gas({
                "from": account.address,
            })

            latest_block = w3.eth.get_block("latest")
            base_fee = latest_block.get("baseFeePerGas", w3.to_wei(1, "gwei"))
            max_priority_fee = w3.to_wei("2", "gwei")
            max_fee = base_fee + max_priority_fee * 2
                
            try:
                tx = contract_obj.functions.registerValidator(new_validator_address_checksum).build_transaction({
                    "from": account.address,
                    "nonce": w3.eth.get_transaction_count(account.address),
                    "gas": int(estimated_gas * 1.2),
                    "maxFeePerGas": max_fee,
                    "maxPriorityFeePerGas": max_priority_fee,
                    "type": 2,
                })
                signed_tx = w3.eth.account.sign_transaction(tx, private_key=private_key)
                tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

                print(f"Sent transaction: {tx_hash.hex()}")

                receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

                if receipt.status == 1:
                    print(f'validator {new_validator_address} added successfully.')
                    return True
            except Exception as e:
                raise Exception(f"Failed to build transaction: {e}")
    else:
        raise Exception("No new validator address provided.")

def deploy_contract(
    private_key, 
    network,
    contract_file, 
    output_values=['abi', 'bin'], 
    constructor_args=None,
    solidity_version='0.8.19',
    save_env_key_base=None,
    save_env_path='.env'
):
    if not contract_file.endswith('.sol'):
        contract_file = contract_file + '.sol'

    path = os.path.join('contracts', contract_file)

    # Install compiler version
    install_solc(solidity_version)
    set_solc_version(solidity_version)

    # Connect to network
    w3, _ = network_func(network=network, ALCHEMY_API_KEY=os.getenv('ALCHEMY_API_KEY'), PRIVATE_KEY=private_key)

    # Load account
    account = w3.eth.account.from_key(private_key)

    # Read and compile contract
    with open(path, 'r', encoding='utf-8') as f:
        solidity_code = f.read()

    compiled_sol = compile_source(
        solidity_code,
        output_values=output_values
    )

    print("Compiled contracts:", compiled_sol.keys())

    contract_file_name = contract_file.replace('.sol', '')

    contract_key = next(
        (key for key in compiled_sol.keys() if contract_file_name in key.split(":")[-1]),
        None
    )
    if not contract_key:
        raise Exception(f"Contract {contract_file_name} not found in compiled sources. Available keys: {list(compiled_sol.keys())}")

    print(f"Using contract key: {contract_key}")
    contract_interface = compiled_sol[contract_key]
    contract_abi = contract_interface['abi']
    bytecode = contract_interface['bin']

    contract_obj = w3.eth.contract(abi=contract_abi, bytecode=bytecode)

    estimated_gas = contract_obj.constructor(**(constructor_args or {})).estimate_gas({
        "from": account.address
    })

    latest_block = w3.eth.get_block("latest")
    base_fee = latest_block.get("baseFeePerGas", w3.to_wei(1, "gwei"))
    max_priority_fee = w3.to_wei("2", "gwei")
    max_fee = base_fee + max_priority_fee * 2

    tx = contract_obj.constructor(**(constructor_args or {})).build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gas": int(estimated_gas * 1.2),
        "maxFeePerGas": max_fee,
        "maxPriorityFeePerGas": max_priority_fee,
        "type": 2,
    })

    estimated_cost = int(estimated_gas * 1.2) * max_fee
    native_balance = w3.eth.get_balance(account.address)

    if native_balance < estimated_cost:
        raise Exception(
            f"Insufficient native gas token balance on {network}. "
            f"Have: {w3.from_wei(native_balance, 'ether')} - Need: {w3.from_wei(estimated_cost, 'ether')}"
        )

    signed_tx = w3.eth.account.sign_transaction(tx, private_key=private_key)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

    print(f"Sent transaction: {tx_hash.hex()}")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    if receipt.status == 1:
        contract_address = receipt.contractAddress
        print(f"Contract deployed successfully at: {contract_address}")

        # Save ABI (optional)
        abi_file_path = os.path.join('abi', f"{contract_file.replace('.sol','')}_{network.upper()}_abi.json")
        os.makedirs(os.path.dirname(abi_file_path), exist_ok=True)
        with open(abi_file_path, 'w') as f:
            json.dump(contract_abi, f, indent=2)
        print(f"ABI saved at {abi_file_path}")

        # Save to env file if requested
        if save_env_key_base:
            save_key_name = f"{save_env_key_base.upper()}_{network.upper()}"
            set_key(dotenv_path=save_env_path, key_to_set=save_key_name, value_to_set=contract_address)
            print(f"Environment variable '{save_key_name}' updated in {save_env_path}")

        return contract_address, abi_file_path
    else:
        raise Exception(f"Contract deployment failed. Receipt: {receipt}")
    
def is_validator(w3, VALIDATOR_REGISTRY_ADDRESS, abi_data, account):

    contract_obj = w3.eth.contract(address=VALIDATOR_REGISTRY_ADDRESS,abi=abi_data)

    owner = contract_obj.functions.owner().call()
    validator_count = contract_obj.functions.getValidatorCount().call()
    validator_registry = contract_obj.functions.getValidators().call()

    print(F'validator_count: {validator_count}')
    print(F'validator_registry: {validator_registry}')

    if account.address in validator_registry:
        is_validator = True
        print(f"Validator {account.address} is registered.")
    else:
        is_validator = False
        raise Exception(f"Validator {account.address} is not registered on chainId {w3.eth.chain_id}.")
    
    return is_validator, owner, validator_count, validator_registry

def wait_for_finalization_event(w3, contract, settlement_id, poll_interval=3, timeout=60):
    """
    Waits for a SettlementFinalized event using block polling.
    More resilient for networks like Ethereum/Sepolia where logs may not appear immediately.
    """
    print(f"Waiting for finalization of settlement {settlement_id}...")
    start_time = time.time()
    from_block = w3.eth.block_number
    end_time = start_time + timeout

    while time.time() < end_time:
        try:
            current_block = w3.eth.block_number
            # We query a range of blocks, widening the window if needed
            logs = contract.events.SettlementFinalized().get_logs(
                from_block=max(from_block - 5, 0),
                to_block=current_block
            )

            for log in logs:
                if log.args.settlementId == settlement_id:
                    print(f"✅ Finalization detected! Status: {log.args.finalStatus}")
                    return log.args.finalStatus

            time.sleep(poll_interval)
        except Exception as e:
            if isinstance(e.args[0], dict) and e.args[0].get("code") == -32000:
                print(f"⚠️ Skipping block fetch error: {e}")
            else:
                print(f"❌ Unexpected error: {e}")
            time.sleep(poll_interval)

    raise TimeoutError(f"❌ Timeout: SettlementFinalized event not detected within {timeout} seconds.")

def create_wallet():
    """Create a new wallet."""
    private_key, address = generate_wallet()
    return private_key, address

def handle_attestation(w3, contract, account, event, processed_settlements, max_retries=3, retry_delay=3):
    settlement_id = event["args"]["settlementId"]

    if settlement_id in processed_settlements:
        print(f"[{w3.provider.endpoint_uri}] 🔁 Skipping already-processed {settlement_id}")
        return

    print(f"[{w3.provider.endpoint_uri}] Detected Attested: {settlement_id}")

    agree = True # Placeholder for now, we assume the validator agrees with the attestation

    for attempt in range(1, max_retries + 1):
        try:
            nonce = w3.eth.get_transaction_count(account.address, 'pending')
            base_fee = w3.eth.get_block("latest").get("baseFeePerGas", w3.to_wei("1", "gwei"))
            priority_fee = w3.to_wei("2", "gwei")
            max_fee = base_fee + 2 * priority_fee

            tx = contract.functions.voteOnSettlement(settlement_id, agree).build_transaction({
                "from": account.address,
                "nonce": nonce,
            })

            estimated_gas = w3.eth.estimate_gas(tx)
            tx['gas'] = int(estimated_gas * 1.2)
            tx['maxPriorityFeePerGas'] = priority_fee
            tx['maxFeePerGas'] = max_fee
            tx['type'] = 2

            signed = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

            if receipt.status == 1:
                processed_settlements.add(settlement_id)
                print(f"[{w3.provider.endpoint_uri}] ✅ Voted on {settlement_id}, tx: {receipt.transactionHash.hex()}")
                return
            else:
                raise Exception("Transaction failed (status = 0)")
        except Exception as e:
            msg = str(e)

            # Detect "Already voted" revert reason
            if "Already voted" in msg:
                print(f"[{w3.provider.endpoint_uri}] 🔁 Already voted on {settlement_id}. Skipping.")
                processed_settlements.add(settlement_id)
                return

            print(f"[{w3.provider.endpoint_uri}] ⚠️ Attempt {attempt} failed for {settlement_id}: {msg}")
            if attempt < max_retries:
                time.sleep(retry_delay)
            else:
                print(f"[{w3.provider.endpoint_uri}] ❌ All attempts failed for {settlement_id}")

def get_last_block_path(network):
    LAST_BLOCKS_DIR = "./last_blocks"
    os.makedirs(LAST_BLOCKS_DIR, exist_ok=True)
    return os.path.join(LAST_BLOCKS_DIR, f"{network}.json")

def load_last_block(network, default):
    path = get_last_block_path(network)
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return json.load(f).get("last_block", default)
        except Exception:
            pass
    return default

def save_last_block(network, block_number):
    path = get_last_block_path(network)
    with open(path, 'w') as f:
        json.dump({"last_block": block_number}, f)

def start_listener(network, private_key, config, ALCHEMY_API_KEY):
    print(f"[{network.upper()}] Connecting...")
    processed_settlements = set()

    w3, account = network_func(network=network, ALCHEMY_API_KEY=ALCHEMY_API_KEY, PRIVATE_KEY=private_key)

    registry_address = config[network]['registry_addresses']['SettlementRegistry']
    registry_abi = config[network]['abis']['SettlementRegistry']

    validator_address = config[network]['registry_addresses']['ValidatorRegistry']
    validator_abi = config[network]['abis']['ValidatorRegistry']

    is_validator(w3, validator_address, validator_abi, account)
    print(f"[{network.upper()}] Connected to {w3.provider.endpoint_uri} as {account.address}")

    try:
        contract = w3.eth.contract(address=registry_address, abi=registry_abi)
        print(f"[{network.upper()}] 🟢 Listening for Attested events...")
    except Exception as e:
        print(f"[{network.upper()}] ❌ Failed to initialize listener: {e}")
        return

    if network.lower() == 'blockdag':
        last_block = load_last_block(network, w3.eth.block_number - 1)
        while True:
            try:
                current_block = w3.eth.block_number
                if current_block > last_block:
                    try:
                        events = contract.events.Attested.get_logs(from_block=last_block + 1, to_block=current_block)
                        for event in events:
                            handle_attestation(w3, contract, account, event, processed_settlements)
                        last_block = current_block
                        save_last_block(network, last_block)
                    except ValueError as e:
                        if isinstance(e.args[0], dict) and e.args[0].get("code") == -32000:
                            print(f"[{network.upper()}] ⚠️ Skipped unavailable block range {last_block+1} to {current_block}")
                        else:
                            raise
                time.sleep(3)
            except Exception as e:
                print(f"[{network.upper()}] ⚠️ Error: {e}")
                time.sleep(5)

    else:
        def create_filter_with_retry():
            for attempt in range(5):
                try:
                    return contract.events.Attested.create_filter(from_block='latest')
                except Exception as e:
                    wait = 2 ** attempt + random.random()
                    print(f"[{network.upper()}] ⚠️ Filter creation failed ({e}) - retrying in {wait:.1f}s...")
                    time.sleep(wait)
            raise RuntimeError("❌ Could not create filter after retries")

        def safe_get_entries(event_filter, retries=5):
            for attempt in range(retries):
                try:
                    return event_filter.get_new_entries()
                except ValueError as e:
                    if "filter not found" in str(e).lower():
                        raise RuntimeError("FilterExpired")
                    raise
                except (RequestsConnectionError, req_ex.SSLError, TimeExhausted) as e:
                    wait = 2 ** attempt + random.random()
                    print(f"[{network.upper()}] 🌐 RPC issue: {e} - retrying in {wait:.1f}s")
                    time.sleep(wait)
            raise RuntimeError("MaxRetriesExceeded")

        event_filter = create_filter_with_retry()

        while True:
            try:
                try:
                    entries = safe_get_entries(event_filter)
                except RuntimeError as e:
                    if str(e) == "FilterExpired":
                        print(f"[{network.upper()}] 🔁 Filter expired. Recreating...")
                        event_filter = create_filter_with_retry()
                        continue
                    else:
                        raise

                for event in entries:
                    handle_attestation(w3, contract, account, event, processed_settlements)

            except Exception as e:
                print(f"[{network.upper()}] ⚠️ Listener error: {e}")
                time.sleep(5)

            time.sleep(3)






