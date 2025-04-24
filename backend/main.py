from flask import Flask, request, jsonify, render_template
import os
import json
import datetime as dt
from datetime import timedelta
from dotenv import load_dotenv

from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions

from chainsettle import (create_link_token,create_plaid_client, github_tag_exists, github_file_exists,
                         simulate_plaid_tx_and_get_access_token)

load_dotenv()

PORT = os.getenv('PORT', 5045)
GIT_COMMIT = os.getenv('GIT_COMMIT_HASH', 'unknown')
BUILD_TIME = os.getenv('BUILD_TIME', 'unknown')

ESCROW_STORE_PATH = "./escrows" 

# Flask App Factory
def create_app():
    app = Flask(__name__)

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
    
    @app.route("/api/create_link_token", methods=["GET"])
    def create_token():
        link_token = create_link_token()
        return jsonify({"link_token": link_token})
    
    @app.route("/api/exchange_token", methods=["POST"])
    def exchange_token():
        data = request.get_json()
        public_token = data.get("public_token")
        escrow_id = data.get("escrow_id")

        if not public_token or not escrow_id:
            return jsonify({"error": "Missing required fields"}), 400

        client = create_plaid_client()
        request_data = ItemPublicTokenExchangeRequest(public_token=public_token)
        response = client.item_public_token_exchange(request_data)

        access_token = response['access_token']
        item_id = response['item_id']

        os.makedirs(ESCROW_STORE_PATH, exist_ok=True)
        with open(f"{ESCROW_STORE_PATH}/{escrow_id}.json", "w") as f:
            json.dump({
                "escrow_id": escrow_id,
                "access_token": access_token,
                "item_id": item_id,
                "timestamp": dt.datetime.utcnow().isoformat()
            }, f)

        return jsonify({
            "status": "linked",
            "escrow_id": escrow_id,
            "item_id": item_id
        })

    @app.route('/api/initiate_attestation', methods=['POST'])
    def init_req():
        data = request.get_json()

        attestation_type = data.get('type')  # 'swift/wire', 'github', etc.

        if attestation_type == 'github':
            owner = data.get('owner')
            repo = data.get('repo')
            tag = data.get('tag')
            path = data.get('path')
            branch = data.get('branch', 'main')

            # Run checks
            tag_ok = github_tag_exists(owner, repo, tag)
            file_ok = github_file_exists(owner, repo, path, branch)

            # Build base response
            base_response = {
                "repo": f"{owner}/{repo}",
                "tag": tag,
                "path": path,
                "branch": branch,
                "tag_confirmed": tag_ok,
                "file_confirmed": file_ok,
                "timestamp": dt.datetime.utcnow().isoformat()
            }

            if tag_ok and file_ok:
                base_response["status"] = "confirmed"
            elif tag_ok:
                base_response["status"] = "partial"
                base_response["message"] = f"Tag exists but file `{path}` not found in `{branch}`"
            elif file_ok:
                base_response["status"] = "partial"
                base_response["message"] = f"File exists but tag `{tag}` not found"
            else:
                base_response["status"] = "unconfirmed"
                base_response["message"] = "Neither tag nor file could be verified"

            return jsonify(base_response)
        
        elif attestation_type == 'plaid':
            escrow_id = data.get("escrow_id")
            amount = data.get("amount")
            reference = data.get("reference", escrow_id)  # Use escrow_id as default ref
            start_date = data.get("start_date", str(dt.date.today() - dt.timedelta(days=2)))
            end_date = data.get("end_date", str(dt.date.today()))

            if not escrow_id or not amount:
                return jsonify({"error": "Missing escrow_id or amount"}), 400

            plaid_client = create_plaid_client()

            # Dynamically simulate the transaction + get access token
            access_token = simulate_plaid_tx_and_get_access_token(plaid_client, float(amount), escrow_id)

            # Search transactions
            
            tx_request = TransactionsGetRequest(
                access_token=access_token,
                start_date=start_date,
                end_date=end_date,
                options=TransactionsGetRequestOptions()
            )

            plaid_response = plaid_client.transactions_get(tx_request)
            transactions = plaid_response["transactions"]

            for tx in transactions:
                tx_amt = float(tx["amount"])
                tx_name = tx.get("name", "")

                if abs(tx_amt - float(amount)) < 0.01 and reference.lower() in tx_name.lower():
                    return jsonify({
                        "status": "confirmed",
                        "transaction_id": tx["transaction_id"],
                        "name": tx_name,
                        "amount": tx_amt,
                        "date": tx["date"]
                    })

            return jsonify({
                "status": "not_found",
                "message": "No matching transaction found",
                "searched": len(transactions)
            })

    return app

if __name__ == "__main__":
    print("Git Commit Hash:", GIT_COMMIT)
    print("Build Timestamp:", BUILD_TIME)
    print('Starting ChainSettle API...')
    app = create_app()
    app.run(host='0.0.0.0', debug=True, use_reloader=False, port=int(PORT))
