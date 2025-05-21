from docusign_esign import ApiClient, EnvelopesApi, RecipientViewRequest
from docusign_esign.client.api_exception import ApiException

from dotenv import load_dotenv
import os
import click
import webbrowser

from chainsettle import create_envelope, get_docusign_client, SUPPORTED_ASSET_CATEGORIES, SUPPORTED_JURISDICTIONS

load_dotenv()

DOCUSIGN_INTEGRATION_KEY = os.getenv("DOCUSIGN_INTEGRATION_KEY")
DOCUSIGN_USER_ID = os.getenv("DOCUSIGN_USER_ID")
PRIVATE_KEY_PATH = '../private.key'
AUTH_SERVER = 'account-d.docusign.com' # 'd' = demo (sandbox)

SCOPES = ['signature', 'impersonation']

@click.group()
def cli():
    pass

@cli.command()
def docusign_test():
    api_client = ApiClient()
    api_client.set_oauth_host_name(AUTH_SERVER)
    with open(PRIVATE_KEY_PATH, 'r') as key_file:
        private_key_bytes = key_file.read()

    # Request access token
    try:
        token_response = api_client.request_jwt_user_token(
            client_id=DOCUSIGN_INTEGRATION_KEY,
            user_id=DOCUSIGN_USER_ID,
            oauth_host_name=AUTH_SERVER,
            private_key_bytes=private_key_bytes,
            expires_in=3600,
            scopes=SCOPES
        )
        access_token = token_response.access_token
    except ApiException as err:
        print(f"OAuth error: {err}")
        return

    print(f"Access Token: {access_token}")

    user_info = api_client.get_user_info(access_token)
    print(f"User Info: {user_info}")
    account_id = user_info.accounts[0].account_id

    api_client.host = user_info.accounts[0].base_uri + "/restapi"
    api_client.set_default_header("Authorization", f"Bearer {access_token}")

    return "Success"

@cli.command()
@click.option('--pdf-path', default="../ChainSettle RWA Tokenization Agreement.pdf", help='Path to the PDF file')
@click.option('--rwa-name', default="rwa-123", help='Name of the RWA')
@click.option('--rwa-issuer', required=True, type=str, help='Issuer of the RWA token')
@click.option('--rwa-value-usd', default=0.0, type=float, help='Value of the RWA in USD')
@click.option('--rwa-category', type=click.Choice(SUPPORTED_ASSET_CATEGORIES), help='RWA type')
@click.option('--rwa-jurisdiction', type=click.Choice(SUPPORTED_JURISDICTIONS), help='Jurisdiction of the RWA')
def create_envelope_cmd(pdf_path, rwa_name, rwa_issuer, rwa_value_usd, rwa_category, rwa_jurisdiction):
    account_id, api_client = get_docusign_client()

    envelope_id = create_envelope(api_client=api_client, 
                                  account_id=account_id,
                                  pdf_path=pdf_path,
                                  rwa_name=rwa_name, 
                                  rwa_issuer=rwa_issuer,
                                  rwa_value_usd=rwa_value_usd,
                                  rwa_category=rwa_category,
                                  rwa_jurisdiction=rwa_jurisdiction)
    print(f"Envelope created: {envelope_id}")

@cli.command()
@click.option('--envelope-id', required=True)
@click.option('--recipient-id', required=True, type=click.Choice(['1', '2'], case_sensitive=False), help='Recipient ID (1 or 2)') 
def simulate_signing(envelope_id, recipient_id):
    account_id, api_client = get_docusign_client()
    envelopes_api = EnvelopesApi(api_client)

    signer_profiles = {
        "1": {
            "client_user_id": "1",
            "recipient_id": "1",
            "user_name": "Signer One",
            "email": "signer1@example.com"
        },
        "2": {
            "client_user_id": "2",
            "recipient_id": "2",
            "user_name": "Signer Two",
            "email": "signer2@example.com"
        }
    }

    if recipient_id not in signer_profiles:
        click.echo("Invalid recipient_id. Use 1 or 2.")
        return

    profile = signer_profiles[recipient_id]

    recipient_view_request = RecipientViewRequest(
        authentication_method='none',
        client_user_id=profile["client_user_id"],
        recipient_id=profile["recipient_id"],
        return_url="https://example.com/return",
        user_name=profile["user_name"],
        email=profile["email"]
    )

    view_url = envelopes_api.create_recipient_view(
        account_id=account_id,
        envelope_id=envelope_id,
        recipient_view_request=recipient_view_request
    )

    click.echo(f"Please sign as {profile['user_name']} at:\n{view_url.url}")
    if click.confirm("Open in browser now?", default=True):
        webbrowser.open(view_url.url)

@cli.command()
@click.option('--envelope-id')
def get_envelope_status(envelope_id):
    account_id, api_client = get_docusign_client()

    envelopes_api = EnvelopesApi(api_client)
    envelope_status = envelopes_api.get_envelope(account_id, envelope_id)
    print(f"Envelope Status: {envelope_status.status}")
    print(f"Envelope Status Type: {type(envelope_status.status)}")

if __name__ == "__main__":
    print(f'[INFO] Starting DocuSign Test...')
    cli()
