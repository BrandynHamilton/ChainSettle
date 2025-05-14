# ChainSettle API Documentation

## Overview
ChainSettle is a Web3 oracle system that verifies off-chain actions (e.g., wire transfers, GitHub commits, PayPal payments) and attests them on-chain. This document describes the available REST API endpoints.

## Base URL
All endpoints are relative to the following base URL:
[https://u2g3350ib1b5120end61cih5l8.ingress.akash-palmito.org](https://u2g3350ib1b5120end61cih5l8.ingress.akash-palmito.org)

## Authentication
- `POST /api/clear_settlement_cache` requires header `X-API-KEY` = `<CACHE_API_KEY>`.
- `POST /add_validator` requires JSON field `api_key` = `<VALIDATOR_API_KEY>`.
- Other endpoints do not require authentication.

## Endpoints

### GET `/`
Returns a welcome HTML page.

**Response**: `text/html`

```html
<h1>ChainSettle API</h1><p>Welcome to the ChainSettle API!</p>
```

### GET `/plaid`
Serves the Plaid link HTML page from `templates/plaid.html`.

**Response**: `text/html`

### POST `/add_validator`
Register a validator node on a supported network. Requires a one-time `api_key`.

**Request JSON**:
```json
{
  "api_key": "<secret_api_key>",
  "network": "<network_name>",
  "validator": "<0x...validator_address>"
}
```

**Responses**:
- `200 OK`:
  ```json
  { "message": "Validator <address> added to <network>. API key invalidated." }
  ```
- `400 Bad Request` or `403 Forbidden`:
  ```json
  { "error": "<message>" }
  ```

### GET `/api/health`
Health check endpoint.

**Response** `200 OK`:
```json
{
  "status": "ok",
  "git_commit": "<git_commit_hash>",
  "build_time": "<build_timestamp>"
}
```

### POST `/api/clear_settlement_cache`
Clear all cached settlements in diskcache.

**Headers**:
```
X-API-KEY: <CACHE_API_KEY>
```

**Response** `200 OK`:
```json
{
  "cleared_settlement_ids": ["id1", "id2", "..."],
  "status": "complete"
}
```

### GET `/api/settlements`
List all settlement IDs from on-chain registries across supported networks.

**Response** `200 OK`:
```json
{ "settlement_ids": ["id1", "id2", "..."] }
```

### GET `/api/get_settlement/<settlement_id>`
Retrieve cached settlement info by ID.

**Path Parameter**: `settlement_id`

**Responses**:
- `200 OK`:
  ```json
  {
    "settlement_id": "<id>",
    "data": { /* settlement info object */ }
  }
  ```
- `404 Not Found`:
  ```json
  { "error": "Settlement ID '<id>' not found" }
  ```

### GET `/api/create_link_token`
Generate a Plaid link token for front-end integration.

**Response** `200 OK`:
```json
{ "link_token": "<token>" }
```

### GET `/paypal-cancel`
Page displayed when a PayPal payment is canceled.

**Response**: `text/html`

### GET `/paypal-success`
PayPal redirection endpoint after approval. Captures and attests the payment on-chain.

**Query Parameter**: `token` = `<PayPal_order_id>`

**Behavior**:
1. Captures the PayPal order.
2. Performs on-chain attestation.
3. Updates cached settlement info.
4. Sends notification email if configured.
5. Renders `paypal.html`.

**Responses**:
- `200 OK`: Rendered HTML on success.
- `400 Bad Request`: Rendered HTML with error details.

### GET `/api/settlement_types`
List supported settlement types and networks.

**Response** `200 OK`:
```json
{
  "supported_types": ["github", "plaid", "paypal"],
  "supported_networks": ["ethereum", "blockdag"]
}
```

### GET `/api/validator_list`
Retrieve the current validator node list for a network.

**Query Parameter**: `network` (optional, default `ethereum`)

**Response** `200 OK`:
```json
{
  "Attest Node": "<owner_address>",
  "Number of Validators": <count>,
  "Validator Registry": "<registry_address>"
}
```

### POST `/api/register_settlement`
Register a new settlement record (GitHub, Plaid, or PayPal).

**Request JSON**:
```json
{
  "settlement_id": "<string>",
  "network": "<string>",
  "settlement_type": "<github|plaid|paypal>",
  "amount": <number>,
  "metadata": "<string>",
  "notify_email": "<email>",
  // GitHub specific:
  "owner": "<github_owner>",
  "repo": "<github_repo>",
  "tag": "<tag>",
  "path": "<file_path>",
  "branch": "<branch>",
  // Plaid specific:
  "public_token": "<plaid_public_token>",
  // PayPal specific:
  "recipient_email": "<email>"
}
```

**Response** `200 OK`:
```json
{
  "status": "registered",
  "settlement_info": { /* settlement info object */ }
}
```

### POST `/api/initiate_attestation`
Initiate the attestation process for a registered settlement.

**Request JSON**:
```json
{ "settlement_id": "<id>" }
```

**Response**:
- `200 OK`: JSON payload depends on settlement type (GitHub, Plaid, PayPal).
- `400 Bad Request`: `{ "error": "<message>" }`

## Error Handling
All error responses return JSON:
```json
{ "error": "<message>" }
```

## Example Usage

**Register a PayPal settlement**:
```bash
curl -X POST https://<host>:<port>/api/register_settlement   -H "Content-Type: application/json"   -d '{
    "settlement_id":"abc123",
    "network":"ethereum",
    "settlement_type":"paypal",
    "amount":100,
    "recipient_email":"user@example.com"
  }'
```

## Contact
For questions or support, reach out at General@ChainSettle.tech.
