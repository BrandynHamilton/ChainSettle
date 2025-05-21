import requests
import time
import os 
import datetime as dt
from datetime import timedelta
import time
from dotenv import load_dotenv, set_key
import json
import smtplib
from email.message import EmailMessage

from chainsettle.web3_utils import attest_onchain, init_attest_onchain

def parse_date(value, fallback):
    if isinstance(value, str):
        return dt.datetime.fromisoformat(value).date()
    elif isinstance(value, dt.date):
        return value
    else:
        return fallback

def format_size(bytes_size):
    for unit in ['bytes','KB','MB','GB']:
        if bytes_size < 1024:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024
    return f"{bytes_size:.1f} TB"

def send_email_notification(subject, body, recipient_email):
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = os.getenv("SMTP_PORT", 587)
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")

    if not all([smtp_server, smtp_user, smtp_password, recipient_email]):
        print("Missing email notification environment variables.")
        return

    msg = EmailMessage()
    msg.set_content(body)
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = recipient_email

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        print(f"✅ Email sent to {recipient_email}")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

def prepare_email_response(base_response):
    status = base_response['finalStatus']
    settlement_id = base_response['settlement_id']

    subject = f"ChainSettle Attestation {settlement_id} Succeeded" if status == 1 else "ChainSettle Attestation Failed"
    body = (
        f"ChainSettle {settlement_id} was successfully attested.\n\nTx Details: {json.dumps(base_response,indent=2)}\n\n"
        if status == 1
        else f"ChainSettle {settlement_id} failed or reverted on-chain.\n\nTx Hash: {json.dumps(base_response,indent=2)}\nPlease review the error receipt or explorer link."
    )

    return subject, body

# Helper functions for onchain settlement registration and attestation
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

def update_settlement_info(cache, settlement_id: str, settlement_info: dict):
    """
    Stores the full settlement_info in cache under settlement_id,
    and appends tx_id to the arweave_tx_map[settlement_id] list.
    """
    # Store latest settlement info under its ID
    cache[settlement_id] = settlement_info

    print(f"[cache] Saved settlement_info and updated tx history for {settlement_id}")

def get_settlement_info(cache, settlement_id: str):
    """Store retrieves latest settlement info by ID"""

    settlement_info = cache.get(settlement_id, None)

    return settlement_info

def is_settlement_initialized_onchain(settlement_id: str, contract) -> bool:
    """
    Returns True if the settlement_id is already initialized onchain.
    """
    onchain_data = contract.functions.settlements(settlement_id).call()
    return onchain_data[0] != ''  # settlementId field

def is_settlement_confirmed_onchain(settlement_id: str, contract) -> bool:
    """
    Returns True if the settlement_id has status 1 (Confirmed).
    """
    onchain_data = contract.functions.settlements(settlement_id).call()
    print(f"Settlement ID: {settlement_id}, Onchain Data: {onchain_data}")
    print(f'onchain_data[2] == 1: {onchain_data[2] == 1}')
    print(f'onchain_data[2]: {onchain_data[2]}')
    print(f"onchain_data type: {type(onchain_data)}")
    for i in onchain_data:
        print(f"onchain_data: {i}")
    return onchain_data[2] == 1  # Status enum: 0=Unverified, 1=Confirmed, 2=Failed

def is_settlement_registered_locally(cache, settlement_id: str) -> bool:
    """
    Returns True if the settlement_id is already in diskcache.
    """
    return cache.get(settlement_id) is not None

def validate_settlement_id_before_registration(cache, settlement_id: str, contract) -> tuple[bool, str]:
    """
    Combines local and onchain checks before allowing a new registration.
    """
    if is_settlement_registered_locally(cache, settlement_id):
        return False, f"Settlement ID '{settlement_id}' already registered in local cache."
    if is_settlement_initialized_onchain(settlement_id, contract):
        return False, f"Settlement ID '{settlement_id}' already exists onchain."
    return True, "OK"

def validate_settlement_id_before_attestation(settlement_id: str, contract) -> tuple[bool, str]:
    """
    Checks if the settlement exists and is not already confirmed.
    """
    if not is_settlement_initialized_onchain(settlement_id, contract):
        return False, f"Settlement ID '{settlement_id}' not initialized onchain."
    if is_settlement_confirmed_onchain(settlement_id, contract):
        return False, f"Settlement ID '{settlement_id}' is already confirmed onchain."
    return True, "OK"
