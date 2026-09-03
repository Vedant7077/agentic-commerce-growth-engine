"""
Razorpay payment integration service.

Creates a Razorpay order for a given Django Order model instance using the
Razorpay Python SDK in TEST mode.

Logic extracted from scripts/create_and_pay.py.
"""

import os

import razorpay

from orders.models import Order


def create_razorpay_order(order: Order) -> dict:
    """Create a Razorpay order for the given Django Order.

    Uses RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET from the environment.
    The amount is taken from ``order.total_paise`` (already in paise).

    Side-effects:
        - Sets ``order.razorpay_order_id`` to the Razorpay order id.
        - Sets ``order.status`` to ``"confirmed"``.
        - Saves the order.

    Returns:
        The raw Razorpay order response dict.

    Raises:
        RuntimeError: If Razorpay credentials are missing.
        razorpay.errors.BadRequestError: If the Razorpay API rejects request.
    """
    key_id = os.environ.get("RAZORPAY_KEY_ID")
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET")

    if not key_id or not key_secret:
        raise RuntimeError(
            "RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET must be set in env. "
            "Get your TEST keys from https://dashboard.razorpay.com/app/keys"
        )

    client = razorpay.Client(auth=(key_id, key_secret))

    order_payload = {
        "amount": order.total_paise,
        "currency": "INR",
        "receipt": order.idempotency_key,
        "notes": {
            "django_order_id": str(order.pk),
        },
    }

    rzp_order: dict = client.order.create(data=order_payload)  # type: ignore[attr-defined]

    # Persist the Razorpay order id back to the Django model
    order.razorpay_order_id = rzp_order["id"]
    order.status = "confirmed"  # type: ignore[assignment]
    order.save(update_fields=["razorpay_order_id", "status"])

    return rzp_order
