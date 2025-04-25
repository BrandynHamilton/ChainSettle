import click
import requests
import webbrowser
import os
import json
import datetime as dt
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

BACKEND_URL = os.getenv('BACKEND_URL', "http://fsoh913eg59c590vufv3qkhod0.ingress.paradigmapolitico.online/") # Defaults to my Akash node 

@click.group()
def cli():
    pass

@cli.command()
@click.option('--type', required=True, type=click.Choice(['plaid', 'github']), help='Type of attestation')
@click.option('--escrow-id', required=True, help='Escrow ID associated with the NFT sale')
@click.option('--network', required=True, type=click.Choice(['ethereum', 'arbitrum', 'optimism']), help="Target chain")
def init_attest(type, escrow_id, network):
    """
    Initializes the Plaid Link flow for a seller. Generates a link_token and opens a browser page.
    """

    res = requests.get(f"{BACKEND_URL}/api/escrows")
    escrow_ids = res.json().get("escrow_ids", [])

    if escrow_id in escrow_ids:
        click.echo(f"Escrow ID '{escrow_id}' already exists. Choose a new one.")
        return

    if type == "plaid":
        try:
            res = requests.get(f"{BACKEND_URL}/api/create_link_token")
            res.raise_for_status()
            link_token = res.json()["link_token"]

            link_url = f"{BACKEND_URL}/link?token={link_token}&escrow_id={escrow_id}&network={network}"
            click.echo(f"Link token created. Open the following URL to link your bank account:\n{link_url}")

            if click.confirm("Open in browser now?", default=True):
                webbrowser.open(link_url)

        except Exception as e:
            click.echo(f"Failed to generate link token: {e}")
    
    elif type == 'github':
        try:
            res = requests.post(f"{BACKEND_URL}/api/register_escrow", json={
                "escrow_id": escrow_id,
                "network": network,
                "type": type
            })
            res.raise_for_status()
            click.echo(f"Escrow {escrow_id} registered on {network}.")
        except requests.RequestException as e:
            try:
                err = e.response.json().get("error") or e.response.text
            except:
                err = str(e)
            click.echo(f"Failed to register escrow: {err}")
            return

@cli.command()
@click.option('--type', required=True, type=click.Choice(['plaid', 'github']), help='Type of attestation')
@click.option('--escrow-id', required=False, help='Escrow ID (required for plaid)')
@click.option('--amount', required=False, type=float, help='Expected transfer amount (plaid only)')
@click.option('--owner', required=False, help='GitHub repo owner (github only)')
@click.option('--repo', required=False, help='GitHub repo name (github only)')
@click.option('--tag', required=False, help='GitHub release tag (github only)')
@click.option('--path', required=False, help='Path to file to verify (github only)')
@click.option('--branch', default='main', help='GitHub branch (optional, default is main)')
def attest(type, escrow_id, amount, owner, repo, tag, path, branch):
    """
    Submit attestation request (plaid or github).
    """
    payload = {"type": type}

    if type == "plaid":
        if not escrow_id or not amount:
            click.echo("escrow-id and amount are required for plaid attestation")
            return

        today = dt.date.today()
        payload.update({
            "escrow_id": escrow_id,
            "amount": amount,
            "start_date": str(today - dt.timedelta(days=3)),
            "end_date": str(today)
        })

    elif type == "github":
        if not (owner and repo and tag and path and escrow_id):
            click.echo("owner, repo, tag, and path are required for github attestation")
            return

        payload.update({
            "owner": owner,
            "repo": repo,
            "tag": tag,
            "path": path,
            "branch": branch,
            "escrow_id":escrow_id
        })

    try:
        res = requests.post(f"{BACKEND_URL}/api/initiate_attestation", json=payload)
        res.raise_for_status()
        data = res.json()

        click.echo(json.dumps(data, indent=2))
    except requests.exceptions.RequestException as e:
        if e.response is not None:
            try:
                err = e.response.json().get("error") or e.response.text
                click.echo(f"Attestation request failed: {err}")
            except Exception:
                click.echo(f"Attestation request failed with status {e.response.status_code}")
        else:
            click.echo(f"Attestation request failed: {e}")

if __name__ == "__main__":
    cli()
