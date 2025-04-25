from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from web3.types import TxParams

def network_func(ALCHEMY_API_KEY, PRIVATE_KEY, chain='ethereum'):
    # Compose Gateway URLs
    ALCHEMY_GATEWAY = f"https://eth-sepolia.g.alchemy.com/v2/{ALCHEMY_API_KEY}"

    w3 = Web3(Web3.HTTPProvider(ALCHEMY_GATEWAY))

    if w3.is_connected():
        try:
            account = w3.eth.account.from_key(PRIVATE_KEY)
            latest_block = w3.eth.get_block('latest')['number']
            print(f"Connected to {chain} with account {account} - Block {latest_block}")
            return w3, account
        except Exception as e:
            print(f"Connected but failed to fetch block. Error: {e}")
    else:
        print(f"Failed to connect to {chain}")

def attest_onchain(w3, account, REGISTRY_ADDRESS, REGISTRY_ABI, amount, escrow_id):

    settlement_registry_obj = w3.eth.contract(address=REGISTRY_ADDRESS, abi=REGISTRY_ABI)

    # === Parameters for attest function ===
    status_enum = 2  # Assuming 2 = "confirmed"
    amount_scaled = int(amount * 1e6)
    details = " "  # or use metadata info if relevant

    # === Build the base tx without gas, to estimate ===
    base_tx = settlement_registry_obj.functions.attest(
        escrow_id,
        status_enum,
        amount_scaled,
        details
    ).build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
    })

    # === Estimate Gas ===
    gas_estimate = w3.eth.estimate_gas(base_tx) 

    # === EIP-1559 Fee Data ===
    latest_block = w3.eth.get_block("latest")
    base_fee = latest_block.get("baseFeePerGas", w3.to_wei(15, "gwei"))
    priority_fee = w3.to_wei(2, "gwei")
    max_fee = base_fee + priority_fee

    # === Final EIP-1559 transaction ===
    tx: TxParams = {
        "from": account.address,
        "to": REGISTRY_ADDRESS,
        "nonce": base_tx["nonce"],
        "data": base_tx["data"],
        "gas": int(gas_estimate * 1.2),  # 20% buffer
        "maxPriorityFeePerGas": priority_fee,
        "maxFeePerGas": max_fee,
        "chainId": w3.eth.chain_id,
        "type": 2
    }

    # === Sign + Send ===
    signed_tx = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    print(f"Sent tx: {'0x'+receipt.transactionHash.hex()}")

    return receipt
