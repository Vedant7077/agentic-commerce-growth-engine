from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import AuditEvent
from .serializers import AuditEventSerializer


@api_view(["GET"])
def audit_events_for_order(request, identifier):
    """GET /audit/<identifier>/ — all events for a given order_id or request_id."""
    events = AuditEvent.objects.none()
    if str(identifier).isdigit():
        events = AuditEvent.objects.filter(order_id=int(identifier)).order_by("created_at")

    if not events.exists():
        events = AuditEvent.objects.filter(payload__request_id=str(identifier)).order_by("created_at")

    serializer = AuditEventSerializer(events, many=True)
    return Response(serializer.data)
