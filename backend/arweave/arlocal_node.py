import os
import time
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv, set_key
import arweave

from chainsettle import (get_tx_status, post_to_arweave)

# Load environment variables
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
ENV_PATH = os.path.join(ROOT_DIR, '.env')
load_dotenv(dotenv_path=ENV_PATH)

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
    print(f'data: {data}')
    data_str = data.get('data')
    if not data_str:
        return jsonify({'error': 'No data provided.'}), 400
    
    print(f'data_str: {data_str}')

    try:
        wallet_file_path = 'arweave_keyfile.json'
        wallet = arweave.Wallet(wallet_file_path)
        print(f'wallet: {wallet}')
        tx = post_to_arweave(wallet, data_str)
        print(f'tx: {tx}')
        tx_id = tx.id
        print(f'tx_id: {tx_id}')
        status = requests.get(f"http://localhost:1984/tx/{tx.id}/status")
        print(f'Transaction status: {status}')

        if not tx_id:
            return jsonify({'error': message}), 500
        return jsonify({'tx_id': tx_id, 'status': status.status_code})
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
