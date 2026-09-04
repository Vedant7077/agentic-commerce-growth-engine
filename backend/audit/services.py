import json
import logging
import os

import requests

from .models import AuditEvent

logger = logging.getLogger(__name__)

# Substrings in event_type that should trigger an n8n webhook alert
_ALERT_KEYWORDS = ("failed", "timeout", "blocked")


def record_audit_event(event_type, actor, payload, reason=None, order_id=None):
    """Create and return an AuditEvent row, and notify n8n on failure/block events."""
    if order_id is None and isinstance(payload, dict):
        order_id = payload.get("order_id")
    if reason is None and isinstance(payload, dict):
        reason = payload.get("reason") or payload.get("detail")

    event = AuditEvent.objects.create(
        event_type=event_type,
        actor=actor,
        payload=payload,
        reason=reason,
        order_id=order_id,
    )

    webhook_url = os.environ.get("N8N_WEBHOOK_URL")
    if webhook_url and _should_alert(event_type, payload):
        try:
            requests.post(
                webhook_url,
                json={
                    "event_id": event.id,
                    "event_type": event_type,
                    "actor": actor,
                    "payload": payload,
                    "reason": reason or (payload.get("reason") if isinstance(payload, dict) else None),
                    "order_id": order_id,
                    "created_at": event.created_at.isoformat(),
                },
                timeout=3,
            )
        except Exception as e:
            logger.warning(f"Failed to send n8n webhook alert: {e}")

    return event


def _should_alert(event_type: str, payload) -> bool:
    """Determine whether this event should trigger an n8n webhook alert."""
    # Trigger on event_type containing any alert keyword
    for keyword in _ALERT_KEYWORDS:
        if keyword in event_type:
            return True

    # Also trigger when payload explicitly indicates a BLOCK decision
    if isinstance(payload, dict) and payload.get("decision") == "BLOCK":
        return True

    return False
