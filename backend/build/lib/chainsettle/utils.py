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
