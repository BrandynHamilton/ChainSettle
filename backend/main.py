from flask import Flask, request, jsonify
import requests
import os
import asyncio
import datetime as dt
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

PORT = os.getenv('PORT', 5045)

# Simulated Swift/Wire Transfer Handler
async def wire_api(wire_id, amount, duration=60, poll_interval=15):
    print(f'Starting simulation for wire_id: {wire_id}')
    status = "In Progress"

    start_time = dt.datetime.now()
    end_time = start_time + timedelta(seconds=duration)

    attempts = 0

    while dt.datetime.now() < end_time:
        attempts += 1
        print(f"[Attempt {attempts}] Status: {status} – waiting {poll_interval}s")
        await asyncio.sleep(poll_interval)

    # Final result
    status = "cleared"
    print(f"Wire {wire_id} status: {status}")

    return {
        "wire_id": wire_id,
        "status": status,
        "amount": amount,
        "currency": "USD",
        "sender": {
            "name": "Alice",
            "bank": "CITIUS33"
        },
        "recipient": {
            "name": "DAO Treasury",
            "bank": "BACUPAPA"
        },
        "memo": "REF:CHAINSETTLE::grant-42",
        "timestamp": dt.datetime.utcnow().isoformat()
    }

async def plaid_api(tx_id, amount, duration=30, poll_interval=15):
    print(f'Starting simulation for tx_id: {tx_id}')
    status = "In Progress"

    start_time = dt.datetime.now()
    end_time = start_time + timedelta(seconds=duration)

    attempts = 0

    while dt.datetime.now() < end_time:
        attempts += 1
        print(f"[Attempt {attempts}] Status: {status} – waiting {poll_interval}s")
        await asyncio.sleep(poll_interval)

    # Final result
    status = "cleared"
    print(f"Transaction {tx_id} status: {status}")

    return {
        "tx_id": tx_id,
        "amount": amount,
        "currency": "USD",
        "status": "cleared",
        "memo": "REF:CHAINSETTLE::user123",
        "timestamp": dt.datetime.utcnow().isoformat(),
        "from_account": "acc-001",
        "to_account": "acc-007"
    }

def github_tag_exists(owner: str, repo: str, tag: str) -> bool:
    url = f"https://api.github.com/repos/{owner}/{repo}/tags"
    headers = {"Accept": "application/vnd.github+json"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        tags = [t["name"] for t in response.json()]
        return tag in tags
    return False

def github_file_exists(owner: str, repo: str, path: str, branch="main") -> bool:
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={branch}"
    response = requests.get(url)
    return response.status_code == 200

# Flask App Factory
def create_app():
    app = Flask(__name__)

    @app.route('/api/initiate_attestation', methods=['POST'])
    async def init_req():
        data = request.get_json()

        attestation_type = data.get('type')  # 'swift/wire', 'github', etc.

        if attestation_type == 'wire':
            wire_id = data.get('wire_id', 'mt103-default')
            amount = data.get('amount', 100000)
            result = await wire_api(wire_id, amount)
            return jsonify(result)

        elif attestation_type == 'plaid':
            tx_id = data.get('tx_id', "txn-9911")
            amount = data.get('amount', 100000)
            result = await plaid_api(tx_id, amount)
            return jsonify(result)

        elif attestation_type == 'github':
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

    return app

if __name__ == "__main__":
    print('Starting ChainSettle Mock API...')
    app = create_app()
    app.run(debug=True, use_reloader=False, port=PORT)
