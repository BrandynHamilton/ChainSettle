from textwrap import indent
from flask import Flask, jsonify, render_template, Blueprint, request, redirect
import os
import json
import datetime as dt
import traceback

from datetime import timedelta
from dotenv import load_dotenv
import time
from plaid.exceptions import ApiException
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions

from chainsettle import (create_link_token,create_plaid_client, github_tag_exists, github_file_exists,get_validator_list,
                         simulate_plaid_tx_and_get_access_token,parse_date,network_func,attest_onchain,prepare_email_response,
                         wait_for_transaction_settlement,init_attest_onchain,SUPPORTED_NETWORKS,STATUS_MAP,SUPPORTED_APIS,
                         format_size,post_to_arweave,get_tx_status,wait_for_finalization_event,send_email_notification,
                         PayPalModule,find_settlement_id_by_order,add_validator)

load_dotenv()

SOLIDITY_ENV_PATH = os.path.join(os.getcwd(), 'solidity', '.env')
load_dotenv(dotenv_path=SOLIDITY_ENV_PATH, override=True)

PORT = os.getenv('PORT', 5045)
GIT_COMMIT = os.getenv('GIT_COMMIT_HASH', 'unknown')
BUILD_TIME = os.getenv('BUILD_TIME', 'unknown')

SETTLEMENT_STORE_PATH = "./settlements"
ALCHEMY_API_KEY = os.getenv('ALCHEMY_API_KEY')
PRIVATE_KEY = os.getenv('EVM_PRIVATE_KEY')
SECRET_API_KEY = os.getenv("VALIDATOR_API_KEY")

CONFIG_PATH = os.path.join(os.getcwd(), 'solidity','chainsettle_config.json')
with open(CONFIG_PATH, "r") as f:
    config = json.load(f)

# Verify the addresses (Optional debug prints)
for network, cfg in config.items():
    print(f"[{network.upper()}] Addresses Loaded:")
    for reg_name, address in cfg['registry_addresses'].items():
        print(f"  {reg_name}: {address}")

assert ALCHEMY_API_KEY and PRIVATE_KEY, "Missing Gateway API Key and Wallet Private Key"

def attest_util(tx, url, w3, account, REGISTRY_ADDRESS, REGISTRY_ABI, amount, settlement_id, status_enum, metadata):
    print(f'tx: {tx}')
    settlement_type = tx.get('settlement_type', 'unknown')
    print(f'Settlement Type: {settlement_type}')

    try:
        receipts = attest_onchain(
            w3=w3,
            account=account,
            REGISTRY_ADDRESS=REGISTRY_ADDRESS,
            REGISTRY_ABI=REGISTRY_ABI,
            amount=amount,
            settlement_type=settlement_type,
            settlement_id=settlement_id,
            status_enum=status_enum,
            details=metadata
        )

        attest_tx_hash = '0x' + receipts['attestation_receipt'].transactionHash.hex()
        validate_tx_hash = '0x' + receipts['validation_receipt'].transactionHash.hex()

        print("Waiting for attestation receipt...")
        attest_receipt = w3.eth.wait_for_transaction_receipt(attest_tx_hash, timeout=60)
        print("Waiting for validation receipt...")
        validate_receipt = w3.eth.wait_for_transaction_receipt(validate_tx_hash, timeout=60)

        if attest_receipt.status != 1:
            raise Exception(f"Attestation tx failed. Status: {attest_receipt.status}")
        if validate_receipt.status != 1:
            raise Exception(f"Validation tx failed. Status: {validate_receipt.status}")

        tx['attest_tx_hash'] = attest_tx_hash
        tx['attest_tx_url'] = f"{url}{attest_tx_hash}"
        tx['validate_tx_hash'] = validate_tx_hash
        tx['validate_tx_url'] = f"{url}{validate_tx_hash}"

        return tx

    except Exception as e:
        print(f"Error during attestation: {e}")
        tx['attest_tx_hash'] = None
        tx['attest_tx_url'] = None
        tx['validate_tx_hash'] = None
        tx['validate_tx_url'] = None
        tx['error'] = str(e)

    return tx

def init_attest_util(tx, url, w3, account, REGISTRY_ADDRESS, REGISTRY_ABI, amount, settlement_id, metadata, wait_seconds=3, max_retries=5):
    print(f'tx: {tx}')
    settlement_type = tx.get('settlement_type', 'unknown')
    print(f'Settlement Type: {settlement_type}')

    try:
        receipt = init_attest_onchain(w3, account, REGISTRY_ADDRESS, REGISTRY_ABI, settlement_type, amount, settlement_id, details=metadata)
        tx_hash = '0x' + receipt.transactionHash.hex()
        tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)


        time.sleep(wait_seconds)

        for attempt in range(max_retries):
            try:
                tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
                if tx_receipt.status != 1:
                    raise Exception(f"Transaction failed onchain. Status: {tx_receipt.status}")

                tx['tx_hash'] = tx_hash
                tx['tx_url'] = f"{url}{tx_hash}"

                return tx
            except Exception as e:
                    print(f"Attempt {attempt+1} failed to get receipt: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(2)  # Wait a little before retrying
                    else:
                        raise  # After final attempt, raise error
    except Exception as e:
        print(f"Error during attestation: {e}")
        tx['tx_hash'] = None
        tx['tx_url'] = None
        tx['error'] = str(e)    

# Flask App Factory
def create_app():
    app = Flask(__name__)

    os.makedirs(SETTLEMENT_STORE_PATH, exist_ok=True)

    @app.route("/plaid")
    def link_page():
        return render_template("plaid.html")

    @app.route("/add_validator", methods=["POST"])
    def add_validator_endpoint():
        global SECRET_API_KEY

        data = request.get_json()
        api_key = data.get("api_key")
        print(F'api_key: {api_key}')
        print(F'SECRET_API_KEY: {SECRET_API_KEY}')
        network = data.get("network")
        validator_address = data.get("validator")

        if not api_key or api_key != SECRET_API_KEY:
            return jsonify({"error": "Unauthorized"}), 403

        if not network or not validator_address:
            return jsonify({"error": "Missing network or validator address"}), 400

        try:
            # Remove the API key to prevent reuse
            # allowed_api_keys.remove(api_key)

            add_validator(
                private_key=PRIVATE_KEY,
                network=network,
                new_validator_address=validator_address,
                config=config
            )

            return jsonify({
                "message": f"Validator {validator_address} added to {network}. API key invalidated."
            }), 200

        except Exception as e:
            print("[ERROR] add_validator failed:")
            traceback.print_exc()  # ← This will show the stack trace
            return jsonify({"error": str(e)}), 500

    @app.route("/api/health", methods=["GET"])
    def health_check():
        return jsonify({
            "status": "ok",
            "git_commit": GIT_COMMIT,
            "build_time": BUILD_TIME,
        })

    @app.route("/api/clear_settlement_cache", methods=["POST"])
    def clear_settlement_cache():
        cleared = []
        for filename in os.listdir(SETTLEMENT_STORE_PATH):
            if filename.endswith(".json"):
                path = os.path.join(SETTLEMENT_STORE_PATH, filename)
                try:
                    os.remove(path)
                    cleared.append(filename)
                except Exception as e:
                    print(f"Failed to delete {filename}: {e}")
        return jsonify({
            "cleared_files": cleared,
            "status": "complete"
        }), 200

    @app.route("/api/settlements", methods=["GET"])
    def list_settlements():
        files = os.listdir(SETTLEMENT_STORE_PATH)
        ids = [f.replace(".json", "") for f in files if f.endswith(".json")]
        return jsonify({"settlement_ids": ids})
    
    @app.route("/api/get_settlement/<settlement_id>", methods=["GET"])
    def get_settlement(settlement_id):
        settlement_path = os.path.join(SETTLEMENT_STORE_PATH, f"{settlement_id}.json")
        if not os.path.exists(settlement_path):
            return jsonify({"error": "Settlement not found"}), 404

        with open(settlement_path, "r") as f:
            settlement_info = json.load(f)

        return jsonify(settlement_info)

    @app.route("/api/create_link_token", methods=["GET"])
    def create_token():
        link_token = create_link_token()
        return jsonify({"link_token": link_token})

    @app.route('/paypal-cancel')
    def paypal_cancel():
        return "<h2>Payment Cancelled</h2><script>alert('You cancelled the payment.');</script>"

    @app.route('/paypal-success', methods=["GET"])
    def paypal_success():
        order_id = request.args.get("token")

        print(F'order_id: {order_id}')

        if not order_id:
            return "Missing token (order ID)", 400

        # breakpoint()

        # Find associated settlement
        settlement_id = find_settlement_id_by_order(order_id, SETTLEMENT_STORE_PATH)
        if not settlement_id:
            return "Could not locate associated settlement ID", 400

        SETTLEMENT_PATH = os.path.join(SETTLEMENT_STORE_PATH, f"{settlement_id}.json")
        if not os.path.exists(SETTLEMENT_PATH):
            return f"Settlement ID '{settlement_id}' not found", 400

        with open(SETTLEMENT_PATH, "r") as f:
            settlement_info = json.load(f)

        if settlement_info.get('settlement_type') != 'paypal':
            return "Settlement type is not PayPal", 400

        metadata = settlement_info.get('metadata')
        notify_email = settlement_info.get('notify_email', None)
        network = settlement_info['network']

        paypal = PayPalModule(sandbox=True)

        try:
            # Capture the payment
            capture_details = paypal.capture_order(order_id)
            capture_id = capture_details["purchase_units"][0]["payments"]["captures"][0]["id"]
            net_amount = capture_details["purchase_units"][0]["payments"]["captures"][0]["seller_receivable_breakdown"]["net_amount"]["value"]

            # Proceed with attestation
            REGISTRY_ADDRESS = config[network]['registry_addresses']['SettlementRegistry']
            url = config[network]['explorer_url']
            REGISTRY_ABI = config[network]['abis']['SettlementRegistry']
            w3, account = network_func(network=network, ALCHEMY_API_KEY=ALCHEMY_API_KEY, PRIVATE_KEY=PRIVATE_KEY)

            if paypal.wait_for_transaction_settlement(capture_id):
                status_enum = STATUS_MAP.get("confirmed")
                settlement_info["status"] = "confirmed"
                settlement_info = attest_util(
                    settlement_info, url, w3, account, REGISTRY_ADDRESS, REGISTRY_ABI,
                    int(float(net_amount)), settlement_id, status_enum, metadata
                )

                print(f'settlement_info: {settlement_info}')

                contract = w3.eth.contract(address=REGISTRY_ADDRESS, abi=REGISTRY_ABI)
                status = wait_for_finalization_event(w3, contract, settlement_id)

                settlement_info['finalStatus'] = status
                settlement_info['capture_id'] = capture_id

                with open(SETTLEMENT_PATH, "w") as f:
                    json.dump(settlement_info, f, indent=2)

                if notify_email:
                    subject, body = prepare_email_response(settlement_info)
                    send_email_notification(subject, body, notify_email)

                return render_template("paypal.html", order_id=order_id, capture_id=capture_id), 200

        except Exception as e:
            return render_template(
            "paypal.html",
            order_id=order_id,
            capture_id=capture_id,
            error=str(e)
        ), 400

    @app.route("/api/settlement_types", methods=["GET"])
    def settlement_types():
        return jsonify({
            "supported_types": SUPPORTED_APIS,
            "supported_networks": SUPPORTED_NETWORKS
        })
    
    @app.route("/api/validator_list", methods=["GET"])
    def validator_list():
        network = request.args.get("network", "ethereum")
        if network not in SUPPORTED_NETWORKS:
            return jsonify({"error": f"Unsupported network: {network}"}), 400

        owner, validator_count, validator_registry = get_validator_list(
            private_key=PRIVATE_KEY,
            network=network,
            config=config
        )
        
        return jsonify({"Attest Node":owner, "Number of Validators":validator_count, "Validator Registry": validator_registry})
    
    @app.route("/api/register_settlement", methods=["POST"])
    def register_settlement():
        data = request.get_json()
        settlement_id = data.get("settlement_id")
        network = data.get("network")
        settlement_type = data.get("settlement_type")  # plaid or github
        notify_email = data.get('notify_email', None)
        owner = data.get('owner')
        repo = data.get('repo')
        tag = data.get('tag')
        path = data.get('path')
        branch = data.get('branch', 'main')
        public_token = data.get("public_token", None)
        recipient_email = data.get('recipient_email')

        print(f'recipient_email: {recipient_email}')

        if settlement_type not in SUPPORTED_APIS:
            return jsonify({"error": f"Unsupported settlement type: {settlement_type}. Supported types are {SUPPORTED_APIS}"}), 400

        if not settlement_id or not network or not settlement_type:
            return jsonify({"error": "settlement_id, network, and type are required"}), 400
        
        if network not in ['ethereum','blockdag']:
            return jsonify({"error": f"network unsupported, must choose either ethereum or blockdag"}), 400

        SETTLEMENT_PATH = os.path.join(SETTLEMENT_STORE_PATH, f"{settlement_id}.json")
        if os.path.exists(SETTLEMENT_PATH):
            return jsonify({"error": f"Settlement ID '{settlement_id}' is already registered"}), 400

        try: 
            amount = float(data.get('amount' , 0))
        except (TypeError, ValueError):
            amount = 0.0
        
        try:
            metadata = str(data.get('metadata', ""))
        except:
            metadata = ""

        REGISTRY_ADDRESS = config[network]['registry_addresses']['SettlementRegistry']
        url = config[network]['explorer_url']
        REGISTRY_ABI = config[network]['abis']['SettlementRegistry']
        w3, account = network_func(network=network,ALCHEMY_API_KEY=ALCHEMY_API_KEY, PRIVATE_KEY=PRIVATE_KEY)

        print(f"Account: {account.address}")
        print(f'recipient_email: {recipient_email}')

        settlement_info = {
            "settlement_id": settlement_id,
            "network": network,
            "settlement_type": settlement_type,
            "timestamp": dt.datetime.utcnow().isoformat(),
            'metadata': metadata,
            'amount':amount,
            'notify_email': notify_email,
            'status': "unverified"
        }

        if settlement_type == 'github':
            print(f'Registering GitHub settlement: {owner}/{repo} at tag {tag}')         
            if not all([owner, repo, tag, path]):
                return jsonify({"error": "GitHub attestation requires owner, repo, tag, and path"}), 400  
            settlement_info.update({
                "owner": owner,
                "repo": repo,
                "tag": tag,
                "path": path,
                "branch": branch
            })
        elif settlement_type == 'plaid':
            print(f'Registering Plaid settlement with ID: {settlement_id}')
            if not public_token:
                return jsonify({"error": "Missing public token or settlement id fields"}), 400

            client = create_plaid_client()
            request_data = ItemPublicTokenExchangeRequest(public_token=public_token)
            response = client.item_public_token_exchange(request_data)

            print(f'getting access token, generating tx')
            access_token = simulate_plaid_tx_and_get_access_token(client, float(amount), settlement_id)
            item_id = response['item_id']

            if not access_token:
                return jsonify({"error": "Must pass access_token"}), 400
            settlement_info.update({
                "access_token": access_token,
                "item_id": item_id
            })
        elif settlement_type == 'paypal':
            print(f'recipient_email: {recipient_email}')
            print(f'amount: {amount}')
            print(f'Registering PayPal settlement with ID: {settlement_id} to {recipient_email}')
            if not all([recipient_email]):
                return jsonify({"error": "PayPal attestation requires recipient_email and amount"}), 400
            settlement_info.update({
                "recipient_email": recipient_email,
            })

        settlement_info = init_attest_util(settlement_info, url, w3, account, REGISTRY_ADDRESS, REGISTRY_ABI, amount, settlement_id, metadata)

        with open(SETTLEMENT_PATH, "w") as f:
            json.dump(settlement_info, f)

        return jsonify({"status": "registered", "settlement_info": settlement_info})

    @app.route('/api/initiate_attestation', methods=['POST'])
    def init_req():
        data = request.get_json()

        settlement_id = data.get("settlement_id")
        SETTLEMENT_PATH = os.path.join(SETTLEMENT_STORE_PATH, f"{settlement_id}.json")
        print(f'SETTLEMENT_PATH: {SETTLEMENT_PATH}')
        if not os.path.exists(SETTLEMENT_PATH):
            return jsonify({"error": f"Settlement ID '{settlement_id}' not found"}), 400

        with open(SETTLEMENT_PATH, "r") as f:
            settlement_info = json.load(f)

        print(f'settlement_info: {settlement_info}')

        recipient_email = settlement_info.get('recipient_email')
        owner = settlement_info.get('owner')
        repo = settlement_info.get('repo')
        tag = settlement_info.get('tag')
        path = settlement_info.get('path')
        branch = settlement_info.get('branch', 'main')

        network = settlement_info['network']
        settlement_type = settlement_info['settlement_type']
        amount = settlement_info.get('amount', 0.0)
        notify_email = settlement_info.get('notify_email', None)

        if network not in ['ethereum', 'blockdag']:
            return jsonify({"error": f"network unsupported, must choose either ethereum or blockdag"}), 400

        REGISTRY_ADDRESS = config[network]['registry_addresses']['SettlementRegistry']
        url = config[network]['explorer_url']
        REGISTRY_ABI = config[network]['abis']['SettlementRegistry']

        print(f'NETWORK: {network}, REGISTRY_ADDRESS: {REGISTRY_ADDRESS},   URL: {url}')

        w3, account = network_func(network=network, ALCHEMY_API_KEY=ALCHEMY_API_KEY, PRIVATE_KEY=PRIVATE_KEY)
        latest_block = w3.eth.get_block("latest")
        blocknumber = latest_block['number']

        print(f"Account: {account.address}")

        base_response = {
            "settlement_id": settlement_id,
            "network": network,
            "settlement_type": settlement_type,
        }

        if settlement_type == 'github':
            response_payload = base_response.copy()

            print(f'Initiating GitHub attestation for {owner}/{repo} at tag {tag}')
            tag_ok = github_tag_exists(owner, repo, tag)
            file_ok, size_bytes = github_file_exists(owner, repo, path, branch)

            try:
                existing_metadata = str(data.get('metadata', ""))
            except:
                existing_metadata = ""

            if existing_metadata.strip() != "":
                combined_metadata = f"{existing_metadata} | size: {size_bytes} bytes"
            else:
                combined_metadata = f"size: {size_bytes} bytes"

            print(f'Final metadata: {combined_metadata}')

            response_payload.update({
                "repo": f"{owner}/{repo}",
                "type": "github",
                "tag": tag,
                "path": path,
                "branch": branch,
                "tag_confirmed": tag_ok,
                "file_confirmed": file_ok,
                "timestamp": dt.datetime.utcnow().isoformat(),
                "metadata": combined_metadata
            })

            if tag_ok and file_ok:
                print(f'Github Tag Found! Attesting Onchain...')
                status = "confirmed"
            else:
                print(f"Github Tag: {tag_ok}, File: {file_ok}")
                status = "failed"

            status_enum = STATUS_MAP.get(status)
            response_payload["status"] = status

            response_payload = attest_util(response_payload, url, w3, account, REGISTRY_ADDRESS, REGISTRY_ABI, amount, settlement_id, status_enum, combined_metadata)

            contract = w3.eth.contract(address=REGISTRY_ADDRESS, abi=REGISTRY_ABI)

            status = wait_for_finalization_event(w3, contract, settlement_id)
            response_payload['finalStatus'] = status
            print(f'Final Status: {status}')

            with open(SETTLEMENT_PATH, "w") as f:
                json.dump(response_payload, f, indent=2)

            if notify_email is not None:
                subject, body = prepare_email_response(response_payload)
                print(f'Sending email notification to {notify_email}')
                send_email_notification(subject, body, notify_email)

            return jsonify(response_payload)

        elif settlement_type == 'paypal':
            response_payload = base_response.copy()
            response_payload.update({
                
                "recipient_email": recipient_email,
                "amount": amount,
                "timestamp": dt.datetime.utcnow().isoformat()
            })
            print(f'settlement_info:{settlement_info}')

            try:
                existing_metadata = str(data.get('metadata', ""))
            except:
                existing_metadata = ""

            if existing_metadata.strip() != "":
                combined_metadata = f"{existing_metadata} | recipient: {recipient_email}"
            else:
                combined_metadata = f"recipient: {recipient_email}"

            paypal = PayPalModule(sandbox=True)  # uses PAYPAL_CLIENT_ID/SECRET from env
            # Create order
            order_id, approval_url = paypal.create_order(
                recipient_email=recipient_email,
                amount=float(amount),
                currency="USD",
                metadata=f"settlement {settlement_id} - ChainSettle"
            )

            print(f'order_id: {order_id}')

            settlement_info.update({
                "status": "pending",
                "order_id": order_id,
                "approval_url": approval_url,
                "metadata": combined_metadata
            })

            with open(SETTLEMENT_PATH, "w") as f:
                json.dump(settlement_info, f, indent=2)

            with open(SETTLEMENT_PATH, "r") as f:
                saved_settlement_info = json.load(f)

            print(json.dumps(saved_settlement_info, indent=2))

            return jsonify(
                settlement_info
            ), 200

        elif settlement_type == 'plaid':
            response_payload = base_response.copy()
            print(f'settlement_info:{settlement_info}')

            try:
                metadata = str(data.get('metadata', ""))
            except:
                metadata = ""

            today = dt.date.today()
            start_date = parse_date(data.get("start_date"), today - timedelta(days=3))
            end_date = parse_date(data.get("end_date"), today)

            if not settlement_id or not amount:
                return jsonify({"error": "Missing settlement_id or amount"}), 400

            plaid_client = create_plaid_client()

            access_token = settlement_info.get('access_token')
            if not access_token:
                return jsonify({"error": "Access token not found in settlement info"}), 400

            tx_request = TransactionsGetRequest(
                access_token=access_token,
                start_date=start_date,
                end_date=end_date,
                options=TransactionsGetRequestOptions()
            )

            print(f'Fetching Transactions...')
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

            print(f'Waiting for transaction to settle...')
            matched_tx = wait_for_transaction_settlement(
                plaid_client,
                access_token,
                settlement_id,
                amount,
                start_date,
                end_date
            )

            today_str = dt.date.today().isoformat()
            response_payload.update({
                "status": "confirmed",
                "transaction_id": matched_tx.get("transaction_id") if matched_tx else f"synthetic-{settlement_id}-{int(time.time())}",
                "name": matched_tx.get("name") if matched_tx else f"settlement {settlement_id} payment",
                "amount": float(amount),
                "date": matched_tx.get("date") if matched_tx else today_str,
                "metadata": metadata
            })

            print(f'Transaction Found! Attesting Onchain')

            status_enum = STATUS_MAP.get("confirmed")

            response_payload = attest_util(response_payload, url, w3, account, REGISTRY_ADDRESS, REGISTRY_ABI, amount, settlement_id, status_enum, metadata)

            contract = w3.eth.contract(address=REGISTRY_ADDRESS, abi=REGISTRY_ABI)

            status = wait_for_finalization_event(w3, contract, settlement_id)
            response_payload['finalStatus'] = status
            print(f'Final Status: {status}')

            with open(SETTLEMENT_PATH, "w") as f:
                json.dump(response_payload, f, indent=2)

            if notify_email is not None:
                subject, body = prepare_email_response(response_payload)
                print(f'Sending email notification to {notify_email}')
                send_email_notification(subject, body, notify_email)

            return jsonify(response_payload)
        
    # @app.route("/api/attest/paypal-callback", methods=["GET"])
    # def handle_paypal_callback():
    #     order_id = request.args.get("token")  # token is the PayPal order_id

    #     if not order_id:
    #         return "Missing token (order ID)", 400

    #     # Try to find the associated settlement_id from local store
    #     settlement_id = find_settlement_id_by_order(order_id, SETTLEMENT_STORE_PATH)  # implement this lookup
    #     if not settlement_id:
    #         return "Could not locate associated settlement ID", 400
        
    #     SETTLEMENT_PATH = os.path.join(SETTLEMENT_STORE_PATH, f"{settlement_id}.json")

    #     if not any([order_id, settlement_id]):
    #         return "Missing order ID or Settlement ID", 400
        
    #     print(f'SETTLEMENT_PATH: {SETTLEMENT_PATH}')
    #     if not os.path.exists(SETTLEMENT_PATH):
    #         return jsonify({"error": f"Settlement ID '{settlement_id}' not found"}), 400

    #     with open(SETTLEMENT_PATH, "r") as f:
    #         settlement_info = json.load(f)

    #     if settlement_info.get('settlement_type') != 'paypal':
    #         return jsonify({"error": "Settlement type is not PayPal"}), 400

    #     print(f'settlement_info: {settlement_info}')

    #     metadata = settlement_info.get('metadata')
    #     notify_email = settlement_info.get('notify_email', None)

    #     paypal = PayPalModule(sandbox=True)

    #     try:
    #         capture_details = paypal.capture_order(order_id)
    #         print(f'capture_details" {capture_details}')

    #         # ⬇️ All your existing logic from here
    #         capture_id = capture_details["purchase_units"][0]["payments"]["captures"][0]["id"]
    #         payer_email = capture_details["payer"]["email_address"]
    #         gross_amount = capture_details["purchase_units"][0]["payments"]["captures"][0]["amount"]["value"]
    #         paypal_fee = capture_details["purchase_units"][0]["payments"]["captures"][0]["seller_receivable_breakdown"]["paypal_fee"]["value"]
    #         net_amount = capture_details["purchase_units"][0]["payments"]["captures"][0]["seller_receivable_breakdown"]["net_amount"]["value"]
    #         recipient_email = capture_details["purchase_units"][0]["payments"]["captures"][0]["seller_receivable_breakdown"]["net_amount"]["currency_code"]

    #         print(f"Payment completed with capture ID: {capture_id}")
    #         print(f'payer_email: {payer_email}')
    #         print(f'gross_amount: {gross_amount}')
    #         print(f'paypal_fee: {paypal_fee}')
    #         print(f'net_amount: {net_amount}')

    #         REGISTRY_ADDRESS = config[network]['registry_addresses']['SettlementRegistry']
    #         url = config[network]['explorer_url']
    #         REGISTRY_ABI = config[network]['abis']['SettlementRegistry']

    #         print(f'NETWORK: {network}, REGISTRY_ADDRESS: {REGISTRY_ADDRESS},   URL: {url}')

    #         w3, account = network_func(network=network, ALCHEMY_API_KEY=ALCHEMY_API_KEY, PRIVATE_KEY=PRIVATE_KEY)

    #         if paypal.wait_for_transaction_settlement(capture_id):
    #             status_enum = STATUS_MAP.get("confirmed")
    #             settlement_info["status"] = "confirmed"
    #             settlement_info = attest_util(
    #                 settlement_info, url, w3, account, REGISTRY_ADDRESS, REGISTRY_ABI,
    #                 int(net_amount), settlement_id, status_enum, metadata
    #             )

    #             contract = w3.eth.contract(address=REGISTRY_ADDRESS, abi=REGISTRY_ABI)
    #             status = wait_for_finalization_event(w3, contract, settlement_id)
    #             settlement_info['finalStatus'] = status
    #             settlement_info['capture_id'] = capture_id
    #             print(f'Final Status: {status}')

    #             with open(SETTLEMENT_PATH, "w") as f:
    #                 json.dump(settlement_info, f, indent=2)

    #             if notify_email is not None:
    #                 subject, body = prepare_email_response(settlement_info)
    #                 print(f'Sending email notification to {notify_email}')
    #                 send_email_notification(subject, body, notify_email)

    #             return jsonify(settlement_info), 200

    #     except Exception as e:
    #         return f"❌ Error: {e}", 500

    return app

if __name__ == "__main__":
    print("Git Commit Hash:", GIT_COMMIT)
    print("Build Timestamp:", BUILD_TIME)
    print('Starting ChainSettle API...')
    app = create_app()
    app.run(host='0.0.0.0', debug=True, use_reloader=False, port=int(PORT))
