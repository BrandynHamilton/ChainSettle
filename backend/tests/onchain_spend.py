import requests
from web3 import Web3
import json
import os
from dotenv import load_dotenv
load_dotenv()

from chainsettle import network_func

"""
uv pip install ../../backend
uv run python onchain_spend.py

"""

def estimate_start_block(days_back: int, w3: Web3) -> int:
    avg_block_time = 12  # seconds per block on Ethereum
    sec_back       = days_back * 24 * 60 * 60
    block_back     = sec_back // avg_block_time
    return max(0, w3.eth.block_number - block_back)

def get_event_gas_cost(
    w3: Web3,
    etherscan_api_key: str,
    registry_address: str,
    event_signature: str,
    settlement_id: str,
    days_back: int = 7,
    chain: str = "ethereum"
) -> float:
    """
    Returns the total ETH cost for all transactions emitting `event_signature` 
    for a given settlement_id in the last `days_back` days.
    """
    # 1) Compute the two topics
    topic0 = w3.keccak(text=event_signature).hex()
    id_hash = w3.keccak(text=settlement_id).hex()
    topic0 = topic0 if topic0.startswith("0x") else "0x"+topic0
    id_hash = id_hash if id_hash.startswith("0x") else "0x"+id_hash

    # 2) Figure out how far back to scan
    start_block = estimate_start_block(days_back, w3)

    chain_id_map = {
        "ethereum": 11155111,
        "base": 84532,
        "blockdag":1043
    }

    chainid = chain_id_map.get(chain, 11155111)

    print(f"Searching for event '{event_signature}' with topic0 '{topic0}' and settlement ID '{id_hash}'")

    # 3) Call Etherscan logs endpoint
    base_url = "https://api.etherscan.io/v2/api"
    params = {
        "chainid": chainid,
        "module":    "logs",
        "action":    "getLogs",
        "fromBlock": start_block,
        "toBlock":   "latest",
        "address":   registry_address,
        "topic0":    topic0,
        "topic1":    id_hash,
        "apikey":    etherscan_api_key
    }
    resp = requests.get(base_url, params=params, timeout=10).json()
    logs = resp.get("result", [])

    print(f'logs: {logs}')

    print(f"Found {len(logs)} logs for event '{event_signature}' and settlement ID '{settlement_id}'")

    

    # breakpoint()

    # 4) Sum gasUsed * gasPrice for each matching tx
    total_wei = 0
    for log in logs:
        tx_hash = log["transactionHash"]
        receipt = w3.eth.get_transaction_receipt(tx_hash)
        tx      = w3.eth.get_transaction(tx_hash)
        total_wei += receipt["gasUsed"] * tx["gasPrice"]

    return w3.from_wei(total_wei, "ether")


# ── Usage Example ────────────────────────────────────────────────────────────────

if __name__ == "__main__":

    network = 'base'

    with open(r'C:\Users\brand\projects\chainsettle\core\backend\solidity\chainsettle_config.json', 'r') as file:
        CONFIG = json.load(file)
    # Configure once
    ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")
    w3, account = network_func(os.getenv('PRIVATE_KEY'), network, os.getenv('ALCHEMY_API_KEY'))

    REGISTRY_ADDRESS = CONFIG[network]['registry_addresses']['SettlementRegistry']

    # List the exact event signatures (Solidity-style) you indexed
    events = {
        "Initialized": "SettlementInitialized(bytes32,address,string,string,string,uint256)",
        "Attested":    "Attested(bytes32,address,string,string,uint8,string,uint256)",
        "Finalized":   "SettlementValidated(bytes32,string,uint8)"
    }

    # And any settlement IDs you want to audit
    # settlement_ids = ["docusign12345678912345"]
    settlement_ids = ['sadfv23a']

    # Loop & 
    total_cost = 0
    for sid in settlement_ids:
        print(f"\n--- Gas costs for settlement '{sid}' ---")
        for name, sig in events.items():
            cost = get_event_gas_cost(
                w3=w3,
                etherscan_api_key=ETHERSCAN_API_KEY,
                registry_address=REGISTRY_ADDRESS,
                event_signature=sig,
                settlement_id=sid,
                days_back=30,      # scan last 30 days
                chain=network   # or "mainnet", etc.
            )
            print(f"{name:11s}: {cost:.6f} ETH")

            total_cost += cost
    print(f"\nTotal gas cost for all events: {total_cost:.6f} ETH")
