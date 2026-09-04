"""
Razorpay payment integration service.

Creates a Razorpay order for a given Django Order model instance using the
Razorpay Python SDK in TEST mode.

Logic extracted from scripts/create_and_pay.py.
"""

import logging
import os

import razorpay

from orders.models import Order

logger = logging.getLogger(__name__)


class RazorpayTimeoutError(Exception):
    """Raised when a Razorpay API call times out (or is simulated via FORCE_TIMEOUT)."""
    pass


def _get_razorpay_client() -> razorpay.Client:
    """Build and return a Razorpay client from environment credentials."""
    key_id = os.environ.get("RAZORPAY_KEY_ID")
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET")

    if not key_id or not key_secret:
        raise RuntimeError(
            "RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET must be set in env. "
            "Get your TEST keys from https://dashboard.razorpay.com/app/keys"
        )

    return razorpay.Client(auth=(key_id, key_secret))


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
        RazorpayTimeoutError: If FORCE_TIMEOUT is enabled.
        razorpay.errors.BadRequestError: If the Razorpay API rejects request.
    """
    # --- FORCE_TIMEOUT simulation ---
    if os.environ.get("FORCE_TIMEOUT", "false").lower() == "true":
        raise RazorpayTimeoutError(
            "Simulated Razorpay timeout (FORCE_TIMEOUT=true)"
        )

    client = _get_razorpay_client()

    order_payload = {
        "amount": order.total_paise,
        "currency": "INR",
        "receipt": order.idempotency_key or str(order.pk),
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


def handle_razorpay_timeout(order: Order, request_id: str | None = None) -> dict | None:
    """Recover from a Razorpay timeout by checking before retrying.

    Strategy:
        1. If the Django order already has a ``razorpay_order_id``, fetch it from
           Razorpay to verify whether the order actually succeeded despite the
           timeout. If the fetch succeeds, update the Django order to confirmed
           and return the fetched order data.
        2. If no ``razorpay_order_id`` exists, the API call never reached
           Razorpay — safe to retry once via ``create_razorpay_order()``.
        3. If the fetch fails (order doesn't exist on Razorpay), mark the
           Django order as failed and return None.

    Returns:
        The Razorpay order dict if recovery succeeded, or None if the order
        is unrecoverable.
    """
    from audit.services import record_audit_event

    client = _get_razorpay_client()

    if order.razorpay_order_id:
        # Case 1: We have an ID — check if Razorpay actually created it
        try:
            rzp_order = client.order.fetch(order.razorpay_order_id)  # type: ignore[attr-defined]
            # Order exists on Razorpay — update Django side
            order.status = "confirmed"  # type: ignore[assignment]
            order.save(update_fields=["status"])

            record_audit_event(
                event_type="razorpay_timeout_recovered",
                actor="system",
                payload={
                    "request_id": request_id,
                    "order_id": order.pk,
                    "razorpay_order_id": order.razorpay_order_id,
                    "recovery": "fetched_existing",
                },
                order_id=order.pk,
            )

            logger.info(
                "Razorpay timeout recovered: order %s exists as %s",
                order.pk, order.razorpay_order_id,
            )
            return rzp_order

        except Exception as e:
            # Fetch failed — order doesn't exist on Razorpay
            order.status = "failed"  # type: ignore[assignment]
            order.save(update_fields=["status"])

            record_audit_event(
                event_type="razorpay_timeout_failed",
                actor="system",
                payload={
                    "request_id": request_id,
                    "order_id": order.pk,
                    "razorpay_order_id": order.razorpay_order_id,
                    "error": str(e),
                    "recovery": "fetch_failed",
                },
                order_id=order.pk,
            )

            record_audit_event(
                event_type="payment_timeout_handled",
                actor="system",
                payload={
                    "request_id": request_id,
                    "order_id": order.pk,
                    "razorpay_order_id": order.razorpay_order_id,
                    "error": str(e),
                    "recovery": "fetch_failed",
                    "retried": False,
                    "retry_details": {
                        "action": "fetch",
                        "error": str(e),
                        "status": "failed",
                    },
                },
                reason="Razorpay timeout after retry",
                order_id=order.pk,
            )

            logger.warning(
                "Razorpay timeout: fetch failed for order %s (%s): %s",
                order.pk, order.razorpay_order_id, e,
            )
            return None

    else:
        # Case 2: No razorpay_order_id — the call never reached Razorpay.
        # Safe to retry once.
        try:
            rzp_order = create_razorpay_order(order)

            record_audit_event(
                event_type="razorpay_timeout_recovered",
                actor="system",
                payload={
                    "request_id": request_id,
                    "order_id": order.pk,
                    "razorpay_order_id": rzp_order["id"],
                    "recovery": "retried_successfully",
                },
                order_id=order.pk,
            )

            logger.info(
                "Razorpay timeout recovered via retry: order %s → %s",
                order.pk, rzp_order["id"],
            )
            return rzp_order

        except Exception as e:
            order.status = "failed"  # type: ignore[assignment]
            order.save(update_fields=["status"])

            record_audit_event(
                event_type="razorpay_timeout_failed",
                actor="system",
                payload={
                    "request_id": request_id,
                    "order_id": order.pk,
                    "error": str(e),
                    "recovery": "retry_failed",
                },
                order_id=order.pk,
            )

            record_audit_event(
                event_type="payment_timeout_handled",
                actor="system",
                payload={
                    "request_id": request_id,
                    "order_id": order.pk,
                    "error": str(e),
                    "recovery": "retry_failed",
                    "retried": True,
                    "retry_details": {
                        "attempt": 1,
                        "error": str(e),
                        "status": "failed",
                    },
                },
                reason="Razorpay timeout after retry",
                order_id=order.pk,
            )

            logger.warning(
                "Razorpay timeout: retry also failed for order %s: %s",
                order.pk, e,
            )
            return None
