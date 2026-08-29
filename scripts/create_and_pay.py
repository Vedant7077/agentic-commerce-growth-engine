#!/usr/bin/env python3
"""
create_and_pay.py
=================
Creates a Razorpay order in TEST MODE for ₹499 and prints the order_id.

Usage:
    python scripts/create_and_pay.py

Prerequisites:
    pip install razorpay python-dotenv

Razorpay Order → Payment → Signature lifecycle
------------------------------------------------
1. SERVER creates an Order via the Orders API  →  receives `order_id`
2. BROWSER opens Razorpay Checkout with that `order_id`
3. Customer completes payment on the Checkout modal
4. Razorpay redirects/calls back with:
       • razorpay_order_id
       • razorpay_payment_id
       • razorpay_signature
5. SERVER verifies the signature to confirm authenticity (see verify_payment.py)

GOTCHA — amount is always in the smallest currency unit:
    ₹499.00  →  49900 paise    (multiply by 100)
    $4.99    →  499 cents
    Never pass a float like 499.00 — the API expects an integer.
"""

import os
import sys

import razorpay
from dotenv import load_dotenv

# ── Load credentials from .env ──────────────────────────────────────────────
# python-dotenv looks for a .env in the current working directory by default.
# We explicitly point it at the project root so the script works regardless of
# where you invoke it from.
env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(dotenv_path=env_path)

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
    sys.exit(
        "ERROR: RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET must be set in .env.\n"
        "       Get your TEST keys from https://dashboard.razorpay.com/app/keys"
    )

# ── Initialise the Razorpay client ──────────────────────────────────────────
# The client uses HTTP Basic Auth under the hood:
#     Authorization: Basic base64(key_id:key_secret)
client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

# ── Create an order ─────────────────────────────────────────────────────────
# GOTCHA: `amount` MUST be an integer in paise (smallest currency unit).
#         ₹499 = 49_900 paise.  The API will reject floats or string amounts.
AMOUNT_INR = 499          # human-readable price in rupees
AMOUNT_PAISE = AMOUNT_INR * 100   # what the API actually needs

order_payload = {
    "amount": AMOUNT_PAISE,
    "currency": "INR",
    # `receipt` is your internal reference — useful for reconciliation.
    # Razorpay stores it but never uses it for logic.
    "receipt": "receipt_demo_001",
    # Optional notes — arbitrary key-value pairs (max 15 keys, 256 chars each).
    # Handy for attaching metadata the Growth Agent can read later.
    "notes": {
        "purpose": "hackathon_test",
        "product": "Demo Widget",
    },
}

try:
    order = client.order.create(data=order_payload)
except razorpay.errors.BadRequestError as e:
    sys.exit(f"Razorpay BadRequest: {e}")

# ── Print results ───────────────────────────────────────────────────────────
print("=" * 60)
print("  Razorpay TEST Order Created Successfully")
print("=" * 60)
print(f"  Order ID  : {order['id']}")
print(f"  Amount    : ₹{order['amount'] / 100:.2f} ({order['amount']} paise)")
print(f"  Currency  : {order['currency']}")
print(f"  Status    : {order['status']}")
print(f"  Receipt   : {order['receipt']}")
print("=" * 60)
print()
print("NEXT STEP — complete the payment in your browser:")
print()
print("  1. Open  scripts/checkout.html  in any browser.")
print("  2. The page will prompt for your Key ID and Order ID.")
print(f"     Key ID  :  {RAZORPAY_KEY_ID}")
print(f"     Order ID:  {order['id']}")
print("  3. Use a DOMESTIC Razorpay TEST card to pay:")
print("       Mastercard  : 5267 3181 8797 5449")
print("       (or RuPay   : 6527 6589 0000 1005)")
print("       Expiry      : any future date")
print("       CVV         : any 3 digits")
print("       OTP         : any 4+ digit number")
print()
print("  4. After payment, checkout.html will display the")
print("     razorpay_payment_id and razorpay_signature.")
print("     Pass them to verify_payment.py to confirm.")
print()
print("  Example:")
print("    python scripts/verify_payment.py \\")
print(f"        --order_id {order['id']} \\")
print("        --payment_id pay_XXXXXXXXXXXXXX \\")
print("        --signature XXXXXXXXXXXXXXXX")
