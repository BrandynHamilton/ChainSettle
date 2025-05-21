import base64
from docusign_esign import ApiClient, EnvelopesApi
from docusign_esign.models import (EnvelopeDefinition, Document, Signer, SignHere, Tabs, Recipients,
                                   TextCustomField, CustomFields, Text)
import os
from dotenv import load_dotenv

from docusign_esign.client.api_exception import ApiException

load_dotenv()

DOCUSIGN_INTEGRATION_KEY = os.getenv("DOCUSIGN_INTEGRATION_KEY")
DOCUSIGN_USER_ID = os.getenv("DOCUSIGN_USER_ID")
PRIVATE_KEY_PATH = '../private.key'
AUTH_SERVER = 'account-d.docusign.com' # 'd' = demo (sandbox)

SCOPES = ['signature', 'impersonation']

def get_docusign_client(private_key_path = PRIVATE_KEY_PATH):
    print("Initializing DocuSign client...")
    print(f'Using private key: {private_key_path}')
    api_client = ApiClient()
    api_client.set_oauth_host_name(AUTH_SERVER)
    with open(private_key_path, 'r') as key_file:
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

    return account_id, api_client

def create_envelope(
    api_client,
    account_id,
    rwa_name,
    rwa_issuer,
    rwa_value_usd,
    rwa_category,
    rwa_jurisdiction,
    pdf_path: str = None,
    pdf_bytes: bytes = None
):
    """
    Create and send a DocuSign envelope with RWA metadata embedded as custom fields,
    and two signers each signing on the document. Read-only text tabs render metadata visibly at fixed coordinates.

    Either pdf_bytes or pdf_path must be provided.
    If pdf_bytes is passed, we`ll base64-encode that; otherwise we fall back to pdf_path.

    """
    envelopes_api = EnvelopesApi(api_client)

    if pdf_bytes:
        base64_pdf = base64.b64encode(pdf_bytes).decode("utf-8")
    elif pdf_path:
        with open(pdf_path, "rb") as f:
            base64_pdf = base64.b64encode(f.read()).decode("utf-8")
    else:
        raise ValueError("Must pass either pdf_bytes or pdf_path")

    document = Document(
        document_base64=base64_pdf,
        name="Tokenization Agreement",
        file_extension="pdf",
        document_id="1"
    )

    # SignHere tabs for signer 1 and 2
    sign_here1 = SignHere(document_id="1", page_number="1", x_position="100", y_position="150")
    sign_here2 = SignHere(document_id="1", page_number="1", x_position="100", y_position="250")

    # Read-only text tabs placed by X/Y coordinates at bottom left
    read_only_tabs = [
    Text(
        tab_label="asset_name",
        value=rwa_name,
        locked=True,
        document_id="1",
        page_number="1",
        x_position="50",
        y_position="750"
    ),
    Text(
        tab_label="issuer_name",
        value=rwa_issuer,
        locked=True,
        document_id="1",
        page_number="1",
        x_position="50",
        y_position="730"
    ),
    Text(
        tab_label="asset_value_usd",
        value=str(rwa_value_usd),
        locked=True,
        document_id="1",
        page_number="1",
        x_position="50",
        y_position="710"
    ),
    Text(
        tab_label="asset_category",
        value=rwa_category,
        locked=True,
        document_id="1",
        page_number="1",
        x_position="50",
        y_position="690"
    ),
    Text(
        tab_label="jurisdiction",
        value=rwa_jurisdiction,
        locked=True,
        document_id="1",
        page_number="1",
        x_position="50",
        y_position="670"
    )
]

    # Create signers with both sign and read-only text tabs
    signer1 = Signer(
        email="signer1@example.com",
        name="Signer One",
        recipient_id="1",
        routing_order="1",
        client_user_id="1",
        tabs=Tabs(
            sign_here_tabs=[sign_here1],
            text_tabs=read_only_tabs
        )
    )

    signer2 = Signer(
        email="signer2@example.com",
        name="Signer Two",
        recipient_id="2",
        routing_order="2",
        client_user_id="2",
        tabs=Tabs(
            sign_here_tabs=[sign_here2],
            text_tabs=read_only_tabs
        )
    )

    # Embed RWA metadata as custom fields (invisible to signers)
    custom_fields = CustomFields(
        text_custom_fields=[
            TextCustomField(name="asset_name",      value=rwa_name),
            TextCustomField(name="issuer_name",     value=rwa_issuer),
            TextCustomField(name="asset_value_usd", value=str(rwa_value_usd)),
            TextCustomField(name="asset_category",  value=rwa_category),
            TextCustomField(name="jurisdiction",    value=rwa_jurisdiction)
        ]
    )

    envelope_definition = EnvelopeDefinition(
        email_subject="Please sign the RWA tokenization contract",
        documents=[document],
        recipients=Recipients(signers=[signer1, signer2]),
        custom_fields=custom_fields,
        status="sent"
    )

    # Send the envelope
    results = envelopes_api.create_envelope(
        account_id=account_id,
        envelope_definition=envelope_definition
    )

    return results.envelope_id
