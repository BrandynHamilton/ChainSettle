from chainsettle import PayPalModule
import click

@click.group()
def cli():
    pass

@cli.command()
@click.option('--settlement-id', required=True, help='Settlement ID')
@click.option('--recipient-email', required=True, help='Settlement ID')
@click.option('--amount', required=True, type=float, help='Settlement ID')
def paypal_test(settlement_id, recipient_email, amount):
    # Suppose this is part of a web backend endpoint that initiates a PayPal payment
    paypal = PayPalModule(sandbox=True)  # uses PAYPAL_CLIENT_ID/SECRET from env
    # Create order
    order_id, approval_url = paypal.create_order(
        recipient_email=recipient_email,
        amount=float(amount),
        currency="USD",
        metadata=f"settlement {settlement_id} - ChainSettle"
    )

    click.echo(f"[ChainSettle CLI] PayPal approval URL:\n{approval_url}")

    if click.confirm("Open in browser now?", default=True):
        import webbrowser
        webbrowser.open(approval_url)

    if not click.confirm("Wait for onchain confirmation?", default=True):
        return

    # In the callback or after approval, capture the order to complete the transaction:
    approved = paypal.poll_for_approval(order_id)
    if not approved:
        print("Approval timeout. User did not approve the PayPal order.")
        return

    capture_details = paypal.capture_order(order_id)

    capture_id = capture_details['purchase_units'][0]['payments']['captures'][0]['id']
    print(f"Payment completed with capture ID: {capture_id}")

    print(f"Capture details: {capture_details}")

    payer_email = capture_details["payer"]["email_address"]
    gross_amount = capture_details["purchase_units"][0]["payments"]["captures"][0]["amount"]["value"]
    paypal_fee = capture_details["purchase_units"][0]["payments"]["captures"][0]["seller_receivable_breakdown"]["paypal_fee"]["value"]
    net_amount = capture_details["purchase_units"][0]["payments"]["captures"][0]["seller_receivable_breakdown"]["net_amount"]["value"]

    print(f'payer_email: {payer_email}')
    print(f'gross_amount: {gross_amount}')
    print(f'paypal_fee: {paypal_fee}')
    print(f'net_amount: {net_amount}')

    capture_id = capture_details["purchase_units"][0]["payments"]["captures"][0]["id"]
    if paypal.wait_for_transaction_settlement(capture_id):
        print("Transaction settled and attested on-chain.")

if __name__ == "__main__":
    print(f'[INFO] Starting PayPal Test...')
    cli()
