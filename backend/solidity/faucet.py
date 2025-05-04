import os
import json
from flask import Flask, request, jsonify
from web3 import Web3
from dotenv import load_dotenv
from chainsettle import SUPPORTED_NETWORKS, network_func
import traceback
import time

# Load environment variables
load_dotenv()
PRIVATE_KEY = os.getenv('FAUCET_PRIVATE_KEY')
if not PRIVATE_KEY:
    raise ValueError("FAUCET_PRIVATE_KEY is not set.")
ALCHEMY_API_KEY = os.getenv('ALCHEMY_API_KEY')

CONFIG_PATH = os.path.join(os.getcwd(), 'chainsettle_config.json')
with open(CONFIG_PATH, "r") as f:
    config = json.load(f)

# Flask app
app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return "Welcome to ChainSettle Faucet"

@app.route("/faucet_balance", methods=["GET"])
def faucet_balance():
    try:
        network = request.args.get("network")
        if not network or network not in SUPPORTED_NETWORKS:
            return jsonify({"error": "Missing or invalid network"}), 400

        w3, _ = network_func(network=network, ALCHEMY_API_KEY=ALCHEMY_API_KEY, PRIVATE_KEY=PRIVATE_KEY)
        faucet_address = Web3.to_checksum_address(config[network]["faucet"]["addresses"])
        balance_wei = w3.eth.get_balance(faucet_address)
        balance_eth = w3.from_wei(balance_wei, "ether")

        return jsonify({
            "faucet_address": faucet_address,
            "balance_eth": float(balance_eth),
            "network": network
        }), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/faucet", methods=["POST"])
def faucet_dispense():
    data = request.get_json()
    user_address = data.get("address")
    network = data.get("network")
    print(f"[INFO] Dispensing to {user_address} on {network}")

    if not user_address or not network:
        return jsonify({"error": "Missing address or network"}), 400
    if network not in SUPPORTED_NETWORKS:
        return jsonify({"error": f"Unsupported network: {network}"}), 400

    try:
        w3, account = network_func(network=network, ALCHEMY_API_KEY=ALCHEMY_API_KEY, PRIVATE_KEY=PRIVATE_KEY)
        print(f"[INFO] Account: {account.address}")

        faucet_abi = config[network]['faucet']['abis']
        faucet_address = Web3.to_checksum_address(config[network]['faucet']['addresses'])

        contract = w3.eth.contract(address=faucet_address, abi=faucet_abi)
        owner = contract.functions.owner().call()
        print(f"[INFO] Faucet Owner: {owner}")

        try:
            recipient = Web3.to_checksum_address(user_address)
            cooldown = contract.functions.cooldownPeriod().call()
            last_claimed = contract.functions.lastClaimed(recipient).call()
            now = int(time.time())

            remaining = (last_claimed + cooldown) - now
            if remaining > 0:
                return jsonify({
                    "error": "Address is still in cooldown",
                    "cooldown_seconds_remaining": remaining
            }), 400
        except Exception as e:
            print(f"Error fetching cooldown info: {e}")

        # Get EIP-1559 fee values
        latest_block = w3.eth.get_block("latest")
        base_fee = latest_block.get("baseFeePerGas", w3.to_wei(30, 'gwei'))
        priority_fee = w3.eth.max_priority_fee if hasattr(w3.eth, "max_priority_fee") else w3.to_wei(2, 'gwei')

        tx = contract.functions.dispenseTo(Web3.to_checksum_address(user_address)).build_transaction({
            'from': account.address,
            'maxFeePerGas': base_fee + priority_fee,
            'maxPriorityFeePerGas': priority_fee,
            'chainId': w3.eth.chain_id,
            'type': 2
        })

        try:
            gas_estimate = w3.eth.estimate_gas(tx) 
            print(f"Estimated gas: {gas_estimate}")
        except Exception as e:
            print(f"Gas estimation failed: {e}")
            gas_estimate = 200000

        tx['gas'] = gas_estimate
        tx['nonce'] = w3.eth.get_transaction_count(account.address)

        signed_tx = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        print(f"Transaction hash: {w3.to_hex(tx_hash)}")
        if receipt.status != 1:
            print("Transaction failed")
        
        ox_hash = '0x'+receipt.transactionHash.hex()

        resp = {
            "message": "Funds dispensed",
            "tx_hash": ox_hash,
            "network": network
        }

        print(f"[INFO] Dispensed {ox_hash} to {user_address} on {network}")
        print(f'response: {resp}')
            
        return jsonify(resp), 200

    except Exception as e:
        traceback.print_exc()  # Add this to print full traceback in console
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)
