from .models import AuditEvent


def record_audit_event(event_type, actor, payload, reason=None, order_id=None):
    """Create and return an AuditEvent row."""
    return AuditEvent.objects.create(
        event_type=event_type,
        actor=actor,
        payload=payload,
        reason=reason,
        order_id=order_id,
    )
