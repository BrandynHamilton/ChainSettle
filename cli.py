from logging import raiseExceptions
import click
import requests
import webbrowser
import os
import json
import datetime as dt
from datetime import timedelta
from dotenv import load_dotenv
from urllib.parse import urljoin

from docusign_esign import RecipientViewRequest, EnvelopesApi

import time

from chainsettle import SUPPORTED_APIS, SUPPORTED_NETWORKS, SUPPORTED_ASSET_CATEGORIES, SUPPORTED_JURISDICTIONS

load_dotenv()

BACKEND_URL = os.getenv('BACKEND_URL', "https://app.chainsettle.tech/") # Defaults to main Akash node 
LOCAL_URL = os.getenv('LOCAL_URL')

def poll_for_settlement(settlement_id, max_retries=20, poll_interval=10):
    print(f"Polling for onchain activity for settlement '{settlement_id}'...")

    for attempt in range(max_retries):
        try:
            res = requests.get(f"{BACKEND_URL}/api/get_settlement/{settlement_id}")
            res.raise_for_status()
            data = res.json().get("data", {})

            # Check for all possible tx types
            tx_hashes = {
                "Init": data.get("tx_hash"),
                "Attest": data.get("attest_tx_hash"),
                "Validate": data.get("validate_tx_hash")
            }
            urls = {
                "Init": data.get("tx_url"),
                "Attest": data.get("attest_tx_url"),
                "Validate": data.get("validate_tx_url")
            }

            found_any = False
            for label, tx in tx_hashes.items():
                if tx:
                    found_any = True
                    click.echo(f"{label} transaction found: {tx}")
                    if urls[label]:
                        click.echo(f"{label} Explorer URL: {urls[label]}")

            if found_any:
                return  # Exit polling

        except Exception:
            pass

        time.sleep(poll_interval)

    click.echo(f"Timed out waiting for settlement '{settlement_id}' to post transactions.")

@click.group()
def cli():
    pass

@cli.command()
@click.option('--settlement-type', required=True, type=click.Choice(SUPPORTED_APIS), help='Type of attestation')
@click.option('--settlement-id', required=True, help='Unique identifier for the settlement')
@click.option('--amount', required=False, type=float, default=0.0, help='Expected transfer amount, expected for Plaid, PayPal type')
@click.option('--network', required=True, type=click.Choice(SUPPORTED_NETWORKS), help="Target chain")
@click.option('--payer', required=False, help='Payer blockchain address (optional, must start with 0x)')
@click.option('--owner', required=False, help='GitHub repo owner (github only)')
@click.option('--repo', required=False, help='GitHub repo name (github only)')
@click.option('--tag', required=False, help='GitHub release tag (github only)')
@click.option('--path', required=False, help='Path to file to verify (github only)')
@click.option('--branch', default='main', help='GitHub branch (optional, default is main)')
@click.option('--metadata', required=False, type=str, help='Any metadata or uri to post onchain')
@click.option('--recipient-email', default=None, help='Recipient email (paypal).')
@click.option('--pdf-path', default=None, help='Path to PDF to sign (docusign).')
@click.option('--rwa-name', default="rwa-123", help='Name of the RWA')
@click.option('--rwa-issuer', required=False, type=str, help='Issuer of the RWA token')
@click.option('--rwa-value-usd', default=0.0, type=float, help='Value of the RWA in USD')
@click.option('--rwa-category', type=click.Choice(SUPPORTED_ASSET_CATEGORIES), help='RWA type')
@click.option('--rwa-jurisdiction', type=click.Choice(SUPPORTED_JURISDICTIONS), help='Jurisdiction of the RWA')
@click.option('--notify-email', default=None, help='Email to notify.')
@click.option('--local', is_flag=True, default=False, help='If developing locally, uses env Local URL var.')
def init_attest(settlement_type, settlement_id, amount, network, payer, owner, repo, tag, path, branch, metadata, recipient_email, pdf_path, 
                rwa_name, rwa_issuer, rwa_value_usd, rwa_category, rwa_jurisdiction, notify_email, local):
    """
    Initializes the attestation process.
    """

    global BACKEND_URL

    if local:
        BACKEND_URL = LOCAL_URL or "http://localhost:5045"

    print(f'Using backend URL: {BACKEND_URL}')

    res = requests.get(f"{BACKEND_URL}/api/settlements")
    settlement_ids = res.json().get("settlement_ids", [])

    if metadata is None:
        metadata = ""

    if settlement_id in settlement_ids:
        click.echo(f"Settlement ID '{settlement_id}' already exists. Choose a new one.")
        return

    if settlement_type == "plaid":
        if amount is None:
            raise click.UsageError("Must pass value for amount")
        try:
            res = requests.get(f"{BACKEND_URL}/api/create_link_token")
            res.raise_for_status()
            link_token = res.json()["link_token"]

            link_url = f"{BACKEND_URL}/plaid?token={link_token}&settlement_type={settlement_type}&settlement_id={settlement_id}&amount={amount}&network={network}&metadata={metadata}&notify_email={notify_email}&payer={payer}"
            click.echo(f"Link token created. Open the following URL to link your bank account:\n{link_url}")

            if click.confirm("Open in browser now?", default=True):
                webbrowser.open(link_url)

            if click.confirm("Wait for onchain confirmation?", default=True):
                poll_for_settlement(settlement_id)

        except Exception as e:
            click.echo(f"Failed to generate link token: {e}")
    
    elif settlement_type == 'paypal':
        if not all ([recipient_email, settlement_id, amount]):
            raise click.UsageError("PayPal attestation requires --recipient-email and --settlement_id")

        try:
            res = requests.post(f"{BACKEND_URL}/api/register_settlement", json={
                "recipient_email": recipient_email,
                "amount": amount,
                "settlement_id": settlement_id,
                "network": network,
                "settlement_type": settlement_type,
                "metadata":metadata,
                "notify_email": notify_email,
                "payer": payer
            })
            res.raise_for_status()
            settlement_info = res.json()["settlement_info"]
            click.echo(f"Settlement {settlement_id} registered on {network}.\nSettlement Info: {json.dumps(settlement_info,indent=2)}")
        except requests.RequestException as e:
            try:
                err = e.response.json().get("error") or e.response.text
            except:
                err = str(e)
            click.echo(f"Failed to register settlement: {err}")
            return
    elif settlement_type == 'docusign':
        for field in ("rwa_name", "rwa_issuer", "rwa_category", "rwa_jurisdiction", "pdf_path"):
                if not locals()[field]:
                     raise click.UsageError({"error": f"{field} is required for DocuSign"})
            
        try:
            form_data = {
                "amount":             str(amount),
                "settlement_id":      settlement_id,
                "network":            network,
                "payer":              payer,
                "settlement_type":    settlement_type,
                "rwa_name":           rwa_name,
                "rwa_issuer":         rwa_issuer,
                "rwa_value_usd":      str(rwa_value_usd),
                "rwa_category":       rwa_category,
                "rwa_jurisdiction":   rwa_jurisdiction,
                "metadata":           metadata or "",
                "notify_email":       notify_email or ""
            }

            # 2) Open the PDF and send it as 'pdf' in files
            with open(pdf_path, "rb") as pdf_file:
                files = {"pdf": pdf_file}
                url = urljoin(BACKEND_URL, "/api/register_settlement")

                res = requests.post(url, data=form_data, files=files)
                res.raise_for_status()

            settlement_info = res.json()["settlement_info"]
            click.echo(f"Settlement {settlement_id} registered on {network}.\nSettlement Info: {json.dumps(settlement_info,indent=2)}")
            envelope_id = settlement_info.get("envelope_id")
            click.echo(f"DocuSign envelope created: {envelope_id}")
        except requests.RequestException as e:
            try:
                err = e.response.json().get("error") or e.response.text
            except:
                err = str(e)
            click.echo(f"Failed to register settlement: {err}")
            return
            
    elif settlement_type == 'github':
        if not all([owner, repo, tag, path]):
            raise click.UsageError("GitHub attestation requires --owner, --repo, --tag, and --path")
         
        try:
            res = requests.post(f"{BACKEND_URL}/api/register_settlement", json={
                "owner": owner,
                "repo": repo,
                "tag": tag,
                "path": path,
                "branch": branch,
                "settlement_id": settlement_id,
                "network": network,
                "payer": payer,
                "settlement_type": settlement_type,
                "metadata":metadata,
                "notify_email": notify_email
            })
            res.raise_for_status()
            settlement_info = res.json()["settlement_info"]
            click.echo(f"Settlement {settlement_id} registered on {network}.\nSettlement Info: {json.dumps(settlement_info,indent=2)}")
        except requests.RequestException as e:
            try:
                err = e.response.json().get("error") or e.response.text
            except:
                err = str(e)
            click.echo(f"Failed to register settlement: {err}")
            return

@cli.command()
@click.option('--settlement-id', required=True, help='Settlement ID')
@click.option('--metadata', required=False, type=str, help='Any metadata or uri to post onchain')
@click.option('--local', is_flag=True, default=False, help='If developing locally, uses env Local URL var.')
def attest(settlement_id, metadata, local):
    """
    Submits the attestation request.
    """

    global BACKEND_URL

    if local:
        BACKEND_URL = LOCAL_URL or "http://localhost:5045"

    print(f'Using backend URL: {BACKEND_URL}')

    payload = {}

    if metadata is None:
        metadata = ""

    today = dt.date.today()
    payload.update({
        "settlement_id": settlement_id,
        "start_date": str(today - dt.timedelta(days=3)), # Default to 3 days ago
        "end_date": str(today),
        "metadata": metadata
    })

    try:
        res = requests.post(f"{BACKEND_URL}/api/initiate_attestation", json=payload)
        res.raise_for_status()
        data = res.json()

        if 'status' not in data or data['status'] != 'confirmed':
            click.echo("Unexpected response from backend. Settlement may not be valid or pending further action.")

        click.echo(json.dumps(data, indent=2))

        if 'approval_url' in data:
            click.echo(f"Approval URL: {data['approval_url']}")
            if click.confirm("Open in browser now?", default=True):
                webbrowser.open(data['approval_url'])

            if click.confirm("Wait for onchain confirmation?", default=True):
                poll_for_settlement(settlement_id)

    except requests.exceptions.RequestException as e:
        if e.response is not None:
            try:
                err = e.response.json().get("error") or e.response.text
                click.echo(f"Attestation request failed: {err}")
            except Exception:
                click.echo(f"Attestation request failed with status {e.response.status_code}")
        else:
            click.echo(f"Attestation request failed: {e}")

@cli.command()
@click.option('--envelope-id', required=True)
@click.option('--recipient-id', required=True, type=click.Choice(['1', '2'], case_sensitive=False), help='Recipient ID (1 or 2)')
@click.option('--local', is_flag=True, default=False, help='If developing locally, uses env Local URL var.')
def simulate_signing(envelope_id, recipient_id, local):
    global BACKEND_URL

    if local:
        BACKEND_URL = LOCAL_URL or "http://localhost:5045"

    print(f'Using backend URL: {BACKEND_URL}')

    res = requests.post(f"{BACKEND_URL}/api/simulate_signing", json={
        "envelope_id": envelope_id,
        "recipient_id": recipient_id
    })

    res.raise_for_status()

    data = res.json()
    view_url = data.get("view_url")
    if not view_url:
        click.echo("No view URL found in the response.")
        return

    click.echo(f"Please sign at:\n{view_url}")
    if click.confirm("Open in browser now?", default=True):
        webbrowser.open(view_url)

if __name__ == "__main__":
    cli()
