import requests
import time
import datetime as dt
from datetime import timedelta

# Simulated Swift/Wire Transfer Handler
def wire_api(wire_id, amount, duration=30, poll_interval=15):
    print(f'Starting simulation for wire_id: {wire_id}')
    status = "In Progress"

    start_time = dt.datetime.now()
    end_time = start_time + timedelta(seconds=duration)

    attempts = 0

    while dt.datetime.now() < end_time:
        attempts += 1
        print(f"[Attempt {attempts}] Status: {status} – waiting {poll_interval}s")
        time.sleep(poll_interval)

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

#Simulated plaid transfer hanlder
def plaid_api(tx_id, amount, duration=30, poll_interval=15):
    print(f'Starting simulation for tx_id: {tx_id}')
    status = "In Progress"

    start_time = dt.datetime.now()
    end_time = start_time + timedelta(seconds=duration)

    attempts = 0

    while dt.datetime.now() < end_time:
        attempts += 1
        print(f"[Attempt {attempts}] Status: {status} – waiting {poll_interval}s")
        time.sleep(poll_interval)

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

#Github attestation helper functions
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
