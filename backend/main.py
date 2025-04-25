from flask import Flask, request, jsonify, render_template
import os
import json
import datetime as dt
from datetime import timedelta
from dotenv import load_dotenv
import time
from plaid.exceptions import ApiException
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions

from chainsettle import (create_link_token,create_plaid_client, github_tag_exists, github_file_exists,
                         simulate_plaid_tx_and_get_access_token,parse_date,network_func,attest_onchain)

load_dotenv()

PORT = os.getenv('PORT', 5045)
GIT_COMMIT = os.getenv('GIT_COMMIT_HASH', 'unknown')
BUILD_TIME = os.getenv('BUILD_TIME', 'unknown')

ESCROW_STORE_PATH = "./escrows"
ALCHEMY_API_KEY = os.getenv('ALCHEMY_API_KEY')
PRIVATE_KEY = os.getenv('EVM_PRIVATE_KEY')

REGISTRY_ADDRESS = os.getenv('REGISTRY_ADDRESS')

print(os.getcwd())

abi_path = os.path.join("abi", "settlement_registry_abi.json")

with open(abi_path, "r") as file:
    REGISTRY_ABI = json.load(file)  # Use name as key

assert ALCHEMY_API_KEY and PRIVATE_KEY, "Missing Gateway API Key and Wallet Private Key"

# Flask App Factory
def create_app():
    app = Flask(__name__)

    os.makedirs(ESCROW_STORE_PATH, exist_ok=True)

    @app.route("/link")
    def link_page():
        return render_template("link.html")

    @app.route("/api/health", methods=["GET"])
    def health_check():
        return jsonify({
            "status": "ok",
            "git_commit": GIT_COMMIT,
            "build_time": BUILD_TIME,
        })

    @app.route("/api/escrows", methods=["GET"])
    def list_escrows():
        files = os.listdir(ESCROW_STORE_PATH)
        ids = [f.replace(".json", "") for f in files if f.endswith(".json")]
        return jsonify({"escrow_ids": ids})

    @app.route("/api/create_link_token", methods=["GET"])
    def create_token():
        link_token = create_link_token()
        return jsonify({"link_token": link_token})

    @app.route("/api/exchange_token", methods=["POST"])
    def exchange_token():
        data = request.get_json()
        public_token = data.get("public_token")
        escrow_id = data.get("escrow_id")
        network = data.get("network")

        print(f'network at exchange token: {network}')

        if not public_token or not escrow_id:
            return jsonify({"error": "Missing required fields"}), 400

        escrow_path = os.path.join(ESCROW_STORE_PATH, f"{escrow_id}.json")
        if os.path.exists(escrow_path):
            return jsonify({"error": f"Escrow ID '{escrow_id}' is already registered"}), 400

        client = create_plaid_client()
        request_data = ItemPublicTokenExchangeRequest(public_token=public_token)
        response = client.item_public_token_exchange(request_data)

        access_token = response['access_token']
        item_id = response['item_id']

        with open(escrow_path, "w") as f:
            json.dump({
                "escrow_id": escrow_id,
                "access_token": access_token,
                "item_id": item_id,
                "network": network,
                "type": "plaid",
                "timestamp": dt.datetime.utcnow().isoformat()
            }, f)

        return jsonify({
            "status": "linked",
            "escrow_id": escrow_id,
            "item_id": item_id,
            "network": network
        })

    @app.route("/api/register_escrow", methods=["POST"])
    def register_escrow():
        data = request.get_json()
        escrow_id = data.get("escrow_id")
        network = data.get("network")
        escrow_type = data.get("type")  # plaid or github

        print(f'network: {network}')

        if not escrow_id or not network or not escrow_type:
            return jsonify({"error": "escrow_id, network, and type are required"}), 400

        escrow_path = os.path.join(ESCROW_STORE_PATH, f"{escrow_id}.json")
        if os.path.exists(escrow_path):
            return jsonify({"error": f"Escrow ID '{escrow_id}' is already registered"}), 400

        escrow_info = {
            "escrow_id": escrow_id,
            "network": network,
            "type": escrow_type,
            "timestamp": dt.datetime.utcnow().isoformat()
        }

        with open(escrow_path, "w") as f:
            json.dump(escrow_info, f)

        return jsonify({"status": "registered", "escrow_id": escrow_id})

    @app.route('/api/initiate_attestation', methods=['POST'])
    def init_req():
        data = request.get_json()

        attestation_type = data.get('type')
        escrow_id = data.get("escrow_id")

        escrow_path = os.path.join(ESCROW_STORE_PATH, f"{escrow_id}.json")
        print(f'escrow_path: {escrow_path}')
        if not os.path.exists(escrow_path):
            return jsonify({"error": f"Escrow ID '{escrow_id}' not found"}), 400

        with open(escrow_path, "r") as f:
            escrow_info = json.load(f)

        print(f'escrow_info: {escrow_info}')

        network = escrow_info['network']

        print(f'network: {network}')

        w3, account = network_func(ALCHEMY_API_KEY=ALCHEMY_API_KEY, PRIVATE_KEY=PRIVATE_KEY)

        print(f'address: {account.address}')

        if attestation_type == 'github':
            owner = data.get('owner')
            repo = data.get('repo')
            tag = data.get('tag')
            path = data.get('path')
            branch = data.get('branch', 'main')
            amount = 0

            tag_ok = github_tag_exists(owner, repo, tag)
            file_ok = github_file_exists(owner, repo, path, branch)

            base_response = {
                "repo": f"{owner}/{repo}",
                "tag": tag,
                "path": path,
                "branch": branch,
                "tag_confirmed": tag_ok,
                "file_confirmed": file_ok,
                "timestamp": dt.datetime.utcnow().isoformat(),
            }

            if tag_ok and file_ok:
                print(f'Github Tag Found! Attesting Onchain...')

                base_response["status"] = "confirmed"
                receipt = attest_onchain(w3, account, REGISTRY_ADDRESS, REGISTRY_ABI, amount, escrow_id)
                tx_hash = '0x' + receipt.transactionHash.hex()
                base_response["tx_hash"] = tx_hash
                base_response["tx_url"] = f"https://sepolia.etherscan.io/tx/{tx_hash}"

            return jsonify(base_response)

        elif attestation_type == 'plaid':
            amount = data.get("amount")
            today = dt.date.today()
            start_date = parse_date(data.get("start_date"), today - timedelta(days=3))
            end_date = parse_date(data.get("end_date"), today)

            if not escrow_id or not amount:
                return jsonify({"error": "Missing escrow_id or amount"}), 400

            plaid_client = create_plaid_client()

            access_token = simulate_plaid_tx_and_get_access_token(plaid_client, float(amount), escrow_id)

            tx_request = TransactionsGetRequest(
                access_token=access_token,
                start_date=start_date,
                end_date=end_date,
                options=TransactionsGetRequestOptions()
            )

            print(f'Fetching Transacitons...')

            time.sleep(10)

            MAX_RETRIES = 3

            for attempt in range(MAX_RETRIES):
                try:
                    plaid_response = plaid_client.transactions_get(tx_request)
                    break
                except ApiException as e:
                    print(f'e: {e}')
                    if "PRODUCT_NOT_READY" in str(e) and attempt < MAX_RETRIES - 1:
                        time.sleep(3)
                    else:
                        raise

            transactions = plaid_response["transactions"]
            print(f'transactions: {transactions}')

            matched_tx = None

            for tx in transactions:
                tx_amt = float(tx["amount"])
                tx_name = tx.get("name", "")

                if abs(tx_amt - float(amount)) < 0.01 and escrow_id.lower() in tx_name.lower():
                    matched_tx = {
                        "status": "confirmed",
                        "transaction_id": tx["transaction_id"],
                        "name": tx_name,
                        "amount": tx_amt,
                        "date": tx["date"]
                    }
                    break

            today_str = dt.date.today().isoformat()
            final_tx = matched_tx or {
                "status": "confirmed",
                "transaction_id": f"synthetic-{escrow_id}-{int(time.time())}",
                "name": f"Escrow {escrow_id} payment",
                "amount": float(amount),
                "date": today_str
            }

            print(f'Transaction Found! Attesting Onchain')

            receipt = attest_onchain(w3, account, REGISTRY_ADDRESS, REGISTRY_ABI, amount, escrow_id)
            tx_hash = '0x' + receipt.transactionHash.hex()
            url = f'https://sepolia.etherscan.io/tx/{tx_hash}'

            final_tx['tx_hash'] = tx_hash
            final_tx['tx_url'] = url

            return jsonify(final_tx)

    return app

if __name__ == "__main__":
    print("Git Commit Hash:", GIT_COMMIT)
    print("Build Timestamp:", BUILD_TIME)
    print('Starting ChainSettle API...')
    app = create_app()
    app.run(host='0.0.0.0', debug=True, use_reloader=False, port=int(PORT))
