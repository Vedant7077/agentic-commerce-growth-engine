#!/usr/bin/env python3
"""
verify_payment.py
=================
Fetches a Razorpay payment by ID, then verifies the payment signature to
confirm that the callback came from Razorpay and was not tampered with.

Usage:
    python scripts/verify_payment.py \
        --order_id   order_XXXXXXXXXXXXXX \
        --payment_id pay_XXXXXXXXXXXXXX \
        --signature  XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

Prerequisites:
    pip install razorpay python-dotenv

How Razorpay signature verification works
------------------------------------------
After a successful payment, Razorpay sends back three values:
    • razorpay_order_id
    • razorpay_payment_id
    • razorpay_signature

The signature is an HMAC-SHA256 digest of:
    "{order_id}|{payment_id}"
signed with your key_secret.

Razorpay's SDK helper `verify_payment_signature()` recomputes this HMAC and
compares it to the provided signature.  If they don't match, either:
    1. The callback was forged (security issue), or
    2. You passed the wrong key_secret (config issue).

GOTCHA — never trust the client-side callback alone:
    Always verify on the server side.  A malicious user could fabricate
    the payment_id and order_id in the browser callback.

GOTCHA — signature check vs. payment status:
    A valid signature proves the callback is authentic, but doesn't guarantee
    the payment is "captured".  After verification you should also check
    payment['status'] == 'captured' before fulfilling the order.
"""

import argparse
import json
import os
import sys

import razorpay
from dotenv import load_dotenv

# ── Load credentials ────────────────────────────────────────────────────────
env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(dotenv_path=env_path)

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
    sys.exit(
        "ERROR: RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET must be set in .env.\n"
        "       Get your TEST keys from https://dashboard.razorpay.com/app/keys"
    )

client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

# ── Parse CLI arguments ─────────────────────────────────────────────────────
parser = argparse.ArgumentParser(
    description="Verify a Razorpay payment signature and fetch payment details."
)
parser.add_argument("--order_id", required=True, help="Razorpay order_id (order_XXXX)")
parser.add_argument("--payment_id", required=True, help="Razorpay payment_id (pay_XXXX)")
parser.add_argument("--signature", required=True, help="Razorpay signature from checkout callback")
args = parser.parse_args()

# ── Step 1: Fetch the payment object ────────────────────────────────────────
# This call hits GET /v1/payments/:id and returns the full payment object.
# Useful to inspect: status, method, amount, captured flag, error_code, etc.
print(f"\n→ Fetching payment {args.payment_id} …")
try:
    payment = client.payment.fetch(args.payment_id)
except razorpay.errors.BadRequestError as e:
    sys.exit(f"ERROR: Could not fetch payment — {e}")

print(f"  Status      : {payment.get('status')}")
print(f"  Amount      : ₹{payment.get('amount', 0) / 100:.2f} ({payment.get('amount')} paise)")
print(f"  Method      : {payment.get('method')}")
print(f"  Captured    : {payment.get('captured')}")
print(f"  Order ID    : {payment.get('order_id')}")
print(f"  Description : {payment.get('description')}")

# ── Step 2: Verify the signature ────────────────────────────────────────────
# The SDK computes  HMAC_SHA256(order_id + "|" + payment_id, key_secret)
# and compares it to the provided signature.
#
# GOTCHA: The params dict keys must be EXACTLY as shown below — the SDK
#         uses these literal key names internally.  Using camelCase or other
#         variants will silently fail or raise a KeyError.
verify_params = {
    "razorpay_order_id": args.order_id,
    "razorpay_payment_id": args.payment_id,
    "razorpay_signature": args.signature,
}

print("\n→ Verifying signature …")
try:
    # Returns None on success; raises SignatureVerificationError on failure
    client.utility.verify_payment_signature(verify_params)
except razorpay.errors.SignatureVerificationError as e:
    print("=" * 60)
    print("  ✗ SIGNATURE VERIFICATION FAILED")
    print("=" * 60)
    print(f"  Error: {e}")
    print()
    print("  Possible causes:")
    print("    1. The signature was tampered with or forged.")
    print("    2. You're using the wrong RAZORPAY_KEY_SECRET in .env.")
    print("    3. The order_id / payment_id don't match the signature.")
    print()
    sys.exit(1)

# ── Step 3: Confirm ─────────────────────────────────────────────────────────
print("=" * 60)
print("  ✓ SIGNATURE VERIFIED — payment is authentic")
print("=" * 60)

# GOTCHA: A valid signature ≠ a captured payment.
# In TEST mode with auto-capture, status is usually 'captured' already.
# In LIVE mode you may need to explicitly capture the payment.
if payment.get("status") == "captured":
    print("  Payment is captured — safe to fulfil the order.")
elif payment.get("status") == "authorized":
    print("  Payment is authorized but NOT captured.")
    print("  Call client.payment.capture(payment_id, amount, {'currency': 'INR'})")
    print("  to capture it before the authorization window expires (5 days).")
else:
    print(f"  Payment status is '{payment.get('status')}' — inspect before fulfilling.")

# Dump full payment object for debugging / audit trail
print("\n→ Full payment object (for audit_events.payload):")
print(json.dumps(payment, indent=2, default=str))
