import os
import time
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv, set_key
import json
import arweave
from diskcache import Cache

from chainsettle import (get_tx_status, post_to_arweave)

# Load environment variables
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
ENV_PATH = os.path.join(ROOT_DIR, '.env')
load_dotenv(dotenv_path=ENV_PATH)

cache = Cache(f'{ROOT_DIR}/arweave_cache')

# Configure Arweave to use local ArLocal node
arweave.api_config = {
    'host': 'localhost',
    'port': 1984,
    'protocol': 'http'
}

app = Flask(__name__)

@app.route('/fund', methods=['POST'])
def fund_wallet():
    data = request.get_json()
    address = data.get('address')
    amount = data.get('amount', 1000)  # Default to 1000 AR
    set_env = data.get('set_env', False)

    try:
        if not address:
            wallet_file_path = 'arweave_keyfile.json'
            wallet = arweave.Wallet(wallet_file_path)
            address = wallet.address
            if set_env:
                set_key(ENV_PATH, 'ARWEAVE_ADDRESS', address)
        winston_amount = int(amount * 1e12)
        requests.get(f'http://localhost:1984/mint/{address}/{winston_amount}')
        requests.get('http://localhost:1984/mine')

        # Verify balance
        for _ in range(5):
            res = requests.get(f'http://localhost:1984/wallet/{address}/balance')
            balance = int(res.text) / 1e12
            if balance > 0:
                break
            time.sleep(1)

        return jsonify({'address': address, 'balance': balance})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/post-data', methods=['POST'])
def post_data():
    data = request.get_json()
    settlement_data = data.get('data')         # Now this is a dict, not a string
    settlement_id = data.get('settlement_id')

    if not settlement_data:
        return jsonify({'error': 'No data provided.'}), 400
    if not settlement_id:
        return jsonify({'error': 'No settlement_id provided.'}), 400

    try:
        wallet = arweave.Wallet('arweave_keyfile.json')
        tx = arweave.Transaction(wallet, data=json.dumps(settlement_data).encode('utf-8'))
        tx.add_tag("Content-Type", "application/json")
        tx.add_tag("settlement_id", settlement_id)
        tx.sign()
        tx.send()

        for _ in range(5):
            mine_resp = requests.get("http://localhost:1984/mine")
            status = requests.get(f"http://localhost:1984/tx/{tx.id}/status")
            if status.status_code == 200:
                break
            time.sleep(1)

        tx_id = tx.id
        status = requests.get(f"http://localhost:1984/tx/{tx_id}/status")

        # Update local cache map
        tx_map = cache.get('arweave_tx_map', {})
        tx_map.setdefault(settlement_id, []).append(tx_id)
        cache['arweave_tx_map'] = tx_map

        return jsonify({'tx_id': tx_id, 'status': status.status_code})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@app.route('/get-tx/<settlement_id>', methods=['GET'])
def get_tx_for_settlement(settlement_id):
    try:
        tx_map = cache.get('arweave_tx_map', {})
        tx_ids = tx_map.get(settlement_id)
        if not tx_ids:
            return jsonify({'error': f"No txs found for {settlement_id}"}), 404
        return jsonify({'settlement_id': settlement_id, 'tx_ids': tx_ids})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/map-txs', methods=['GET'])
def list_settlement_tx_map():
    try:
        tx_map = cache.get('arweave_tx_map', {})
        return jsonify(tx_map)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get-data/<tx_id>', methods=['GET'])
def get_data(tx_id):
    try:
        response = requests.get(f"http://localhost:1984/{tx_id}")
        if response.status_code == 200:
            return jsonify({'tx_id': tx_id, 'data': response.text})
        elif response.status_code == 202:
            return jsonify({'message': f"Transaction {tx_id} is pending."}), 202
        elif response.status_code == 404:
            return jsonify({'message': f"Transaction {tx_id} not found."}), 404
        else:
            return jsonify({'error': f"Unexpected response ({response.status_code}): {response.text}"}), response.status_code
    except requests.exceptions.RequestException as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5480)
