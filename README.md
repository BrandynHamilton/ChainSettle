# ChainSettle CLI

ChainSettle is a Web3 oracle system deployed on the Akash network that verifies **off-chain actions** (like wire transfers or GitHub milestones) and **attests them on-chain**, enabling credible trust-minimized settlement for digital goods, DAO payouts, escrow, and more.

ChainSettle es un oráculo Web3 que permite verificar acciones fuera de la cadena (como pagos bancarios o commits en GitHub) y confirmarlas en la blockchain, activando flujos de trabajo descentralizados.

---

## Prerequisites

- Python 3.8+
- pip
- Internet access (to call the ChainSettle API)

---

## Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/BrandynHamilton/chainsettle
cd chainsettle
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Set up .env

You can copy the sample file included:

```bash
cp .env.sample .env
```

By default, `.env.sample` contains a working `BACKEND_URL` pointing to the live Akash node:

```env
BACKEND_URL=http://fsoh913eg59c590vufv3qkhod0.ingress.paradigmapolitico.online/
```

Note: `dotenv` does not automatically load `.env.sample`. You must manually rename or copy it to `.env`.

---

## Using the CLI

### init-attest: Initialize an attestation and optionally link a bank account

```bash
python cli.py init-attest --type plaid --escrow-id test123 --network ethereum
```

- For `plaid`, it will launch a Plaid Link URL to securely link a bank account.
- For `github`, it will register the escrow ID without linking anything.

### attest: Submit the attestation

```bash
# For Plaid:
python cli.py attest --type plaid --escrow-id test123 --amount 100.0

# For GitHub:
python cli.py attest --type github --escrow-id test123 \
  --owner your-org --repo your-repo --tag v1.0.0 --path audit/report.pdf
```

Once the action is verified (transaction or GitHub tag/file), ChainSettle posts the attestation onchain and returns a transaction hash and Etherscan URL.

---

## How It Works

1. You initialize an escrow using `init-attest` and include a unique escrow ID.
2. You perform the off-chain action (e.g., bank transfer, code push).
3. You run `attest` with the unique escrow ID to trigger verification and onchain logging.

ChainSettle will automatically detect the event (via Plaid or GitHub API), and send a signed onchain transaction to the configured settlement registry.  The Settlement Registry can then be queried with the unique escrow ID.  

Example commands can be found in notes/cli_notes.txt

### Test Credentials for the Plaid Interface:

- Bank: First Platypus Bank 
- username: user_good
- password: pass_good

---

## Tech Stack

- Python (Click, dotenv, requests)
- ChainSettle backend (Flask on Akash)
- Plaid Sandbox and GitHub API
- Ethereum smart contract deployed to Sepolia testnet

---

## Deployments

- Settlement Registry (Sepolia Ethereum): 0x3B021184e2E1D05A45480b2AA0A8fbD625a058A6

---

## Next Steps

We are working on:

- Integration with Yappy (Panama)
- More attestation types (e.g., document signatures)
