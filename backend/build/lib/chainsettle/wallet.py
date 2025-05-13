import os
import json
from eth_account import Account
from getpass import getpass

KEYSTORE_DIR = os.path.join(os.getcwd(), "keystores")
os.makedirs(KEYSTORE_DIR, exist_ok=True)

def generate_wallet():
    acct = Account.create()
    return acct.key.hex(), acct.address

def encrypt_keystore(private_key, password):
    acct = Account.from_key(private_key)
    keystore = Account.encrypt(private_key, password)
    path = os.path.join(KEYSTORE_DIR, f"{acct.address}.json")
    with open(path, 'w') as f:
        json.dump(keystore, f)
    return path

def load_keystore(path):
    with open(path, 'r') as f:
        keystore = json.load(f)
    password = getpass(f"Enter password to decrypt {os.path.basename(path)}: ")
    try:
        private_key = Account.decrypt(keystore, password).hex()
        return private_key
    except Exception as e:
        print(f"Decryption failed: {e}")
        return None

def load_or_create_validator_key(env_key, new_wallet=False, account=None):
    if env_key and not new_wallet:
        return env_key

    if not os.path.exists(KEYSTORE_DIR):
        os.makedirs(KEYSTORE_DIR)

    keystore_files = [f for f in os.listdir(KEYSTORE_DIR) if f.endswith('.json')]
    print(f'[INFO] Found {len(keystore_files)} keystore files in {KEYSTORE_DIR}')
    print(f'[INFO] Keystore files: {keystore_files}')

    if not new_wallet:

        if account:
            # Normalize address to lowercase for matching
            account = account.lower()
            matched = [f for f in keystore_files if account in f.lower()]
            if matched:
                path = os.path.join(KEYSTORE_DIR, matched[0])
                try:
                    return load_keystore(path)
                except Exception as e:
                    print(f"[ERROR] Failed to load keystore for {account}: {e}")
            else:
                print(f"[WARN] No keystore file found for account: {account}")

        # Default fallback to first available keystore
        if keystore_files:
            path = os.path.join(KEYSTORE_DIR, keystore_files[0])
            try:
                return load_keystore(path)
            except Exception as e:
                print(f"[ERROR] Failed to load default keystore: {e}")

    # Fallback: create new wallet
    print("[INFO] Creating new wallet...")
    private_key, address = generate_wallet()
    password = getpass("Enter password to encrypt keystore: ")
    encrypt_keystore(private_key, password)
    print(f"[INFO] Wallet created: {address}. Fund this wallet to begin validating.")
    return private_key



