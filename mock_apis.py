from flask import Flask, render_template, request, jsonify
import os
from dotenv import load_dotenv

load_dotenv()

def create_app():
    app = Flask(__name__)

    @app.route('api/plaid_transactions/initiate', methods=['POST'])
    def init_swift_req():
        data = request.json()

        tx_id = data.get('tx_id')
        amount = data.get('amount')
        currency = data.get('currency')
        status = 