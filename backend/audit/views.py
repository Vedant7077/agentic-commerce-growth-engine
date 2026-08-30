from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import AuditEvent
from .serializers import AuditEventSerializer


@api_view(["GET"])
def audit_events_for_order(request, order_id):
    """GET /audit/<int:order_id>/ — all events for a given order."""
    events = AuditEvent.objects.filter(order_id=order_id).order_by("created_at")
    serializer = AuditEventSerializer(events, many=True)
    return Response(serializer.data)
