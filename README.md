# ChainSettle CLI and API

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

# Install via uv
pip install uv  # Only if not already installed
uv pip install ./backend/chainsettle
```

---

## Using the CLI

```bash

# See all CLI options
uv run python cli.py --help

```

### init-attest: Initialize an attestation and optionally link a bank account

```bash
# For plaid
uv run python cli.py init-attest --settlement-type plaid --settlement-id 123 --amount 150000 --network base 

# For github
uv run python cli.py init-attest --settlement-type github --settlement-id 345 --owner BrandynHamilton --repo liquid_domains --tag v1.0.0 --path static/onchain_valuation.js --network ethereum

#For paypal
uv run python cli.py init-attest --settlement-type paypal --settlement-id 678 --amount 25000 --recipient-email treasuryops@defiprotocol.com --network blockdag 
```

- For `plaid`, it will launch a Plaid Link URL to securely link a bank account.
- For `github` and `paypal`, it will register the settlement ID without linking anything.

### attest: Submit the attestation

```bash
uv run python cli.py attest --settlement-id 123

```
- For `paypal`, it will return a payment URL to make the specified payment via PayPal. 

Once the action is verified (transaction or GitHub tag/file), ChainSettle posts the attestation onchain and returns a transaction hash and block explorer URL.

---

## Using the API

### init-attest

A user or program should call https://u2g3350ib1b5120end61cih5l8.ingress.akash-palmito.org/api/register_settlement with at least the following:
- settlement_id (unique string ID)
- network (Ethereum, Base, or BlockDAG)
- settlement_type (Plaid, PayPal, or Github)

For plaid, first call `https://u2g3350ib1b5120end61cih5l8.ingress.akash-palmito.org/api/create_link_token` to obtain a plaid public token. 

The following are optional parameters:
- amount (if not passed, defaults to 0)
- notify_email (email where the attest confirmation will be sent)
- metadata (any arbitrary string to be posted onchain)

Below are specific parameters for each type:

#### Plaid
- public_token (for read-only access to bank account)

#### PayPal
- recipient_email (email where the paypal transaction should be sent)

#### Github
- owner (username for owner of the github repository)
- repo (the github repository name)
- tag 
- path (path to the specific file we want to verify)
- branch (defaults to main)

To programmatically wait until a settlement has been processed onchain, use the helper `poll_for_settlement(settlement_id)` in `cli.py`. This polls the ChainSettle API every few seconds and prints when attestation is confirmed.

### attest

A user or program should call https://u2g3350ib1b5120end61cih5l8.ingress.akash-palmito.org/api/initiate_attestation with the following:
- settlement_id 

The following are optional parameters
- metadata (NOTE, IF METADATA WAS SET IN INIT-ATTEST, THIS WILL WRITE OVER METADATA ONCHAIN)

For paypal, this endpoint will return a payment URL for the user to securely make a payment to the anticipated recipient email.  Once payment is submitted, the ChainSettle node will confirm the payment and attest onchain.

To programmatically wait until a settlement has been processed onchain, use the helper `poll_for_settlement(settlement_id)` in `cli.py`. This polls the ChainSettle API every few seconds and prints when attestation is confirmed.

## How It Works

1. You initialize a settlement using `init-attest` and include a unique settlement ID.
2. You perform the off-chain action (e.g., bank transfer, paypal payment, code push).
3. You run `attest` with the unique settlement ID to trigger verification and onchain logging.

ChainSettle will automatically detect the offchain event (via Plaid, PayPal, or GitHub API), and send a signed onchain transaction to the configured settlement registry (which emits the Attested event).  

ChainSettle Validator nodes will listen for Attested events and validate the API call.  Once the attestation is validated, the SettlementFinalized event will be emitted.

The Settlement Registry can then be queried onchain with the unique settlement ID.  

**The backend can be called directly via the API to be used outside of the CLI.  This enables programmatic use of the ChainSettle node.**

Example commands can be found in notes/cli_notes.txt
Example curl commands can be found in notes/curl_notes.txt

```bash

curl -X POST https://.../api/register_settlement \
     -H "Content-Type: application/json" \
     -d '{"settlement_id":"123", "network":"ethereum", "settlement_type":"github", ...}'
```

### Test Credentials for the Plaid Interface:

- Bank: First Platypus Bank 
- username: user_good
- password: pass_good

### Test Credentials for the PayPal Interface:

- email: sb-w7oqu40942591@personal.example.com
- password: 1eh)_t_N

---

## Tech Stack

- Python (Click, dotenv, Flask, requests, web3)
- Solidity (Settlement, Validator registries)
- Plaid Sandbox, PayPal Sandbox, GitHub API
- Akash/Docker (Cloud deployment)
- HTML/CSS/Javascript (Plaid and PayPal landing pages)

---

## Deployments

### Settlement Registry

| Network            | Address                                      |
|--------------------|----------------------------------------------|
| Sepolia Ethereum   | `0x5b31C9a0AFF568749629F9e16b0Cd6E57794d4D5` |
| Sepolia Base       | `0x8924aa4F75634Cd3c53258C5C998A137FE170b4b` |
| BlockDAG Testnet   | `0x607B24cfBfcCc073B12A610b3950aEE70619e53C` |

### Validator Registry

| Network            | Address                                      |
|--------------------|----------------------------------------------|
| Sepolia Ethereum   | `0x8A37b540eB69C919A09Ae21b20EF43825f650522` |
| Sepolia Base       | `0x837351fFA11fF3C4058d0C1A5d47f4B8b87c67cC` |
| BlockDAG Testnet   | `0x93020601DEfaB09B18da0409833D79F34549f3cE` |

### ChainSettle Attest Node

| Type                  | Value                                                                 |
|-----------------------|-----------------------------------------------------------------------|
| Address               | `0x6fBc41ea9cFF9f1C2DCC8F61e190623d0B1CD7b3`                          |
| URL                   | [Visit](https://u2g3350ib1b5120end61cih5l8.ingress.akash-palmito.org/) |

### ChainSettle Validator Node

| Type                  | Value                                                                 |
|-----------------------|-----------------------------------------------------------------------|
| Address               | `0xE6A5aD9b28Ee9E7B04aC51c397658cF2D9F821F3`                          |
| URL                   | [Visit](http://m39kapikcle29eetnb3ck43r3s.ingress.paradigmapolitico.online/) |
---

## Next Steps

We are working on:

- Onboarding more validators
- More attestation types (e.g. document signatures)

## Contact Info

- [General@ChainSettle.tech](mailto:General@ChainSettle.tech)
