from django.test import TestCase
from rest_framework.test import APIClient

from .models import AuditEvent
from .services import record_audit_event


class AuditEventViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        # Create some audit events for order 42
        record_audit_event(
            event_type="cart_item_added",
            actor="user@example.com",
            payload={"product_id": 1},
            order_id=42,
        )
        record_audit_event(
            event_type="order_created",
            actor="user@example.com",
            payload={"total_paise": 500000},
            order_id=42,
        )
        # Unrelated event for order 99
        record_audit_event(
            event_type="order_created",
            actor="other@example.com",
            payload={"total_paise": 100000},
            order_id=99,
        )

    def test_get_audit_events_for_order(self):
        """GET /audit/42/ returns only events for order 42, ordered by created_at."""
        response = self.client.get("/audit/42/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["event_type"], "cart_item_added")
        self.assertEqual(data[1]["event_type"], "order_created")

    def test_get_audit_events_empty(self):
        """GET /audit/999/ returns an empty list when no events exist."""
        response = self.client.get("/audit/999/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_record_audit_event_service(self):
        """record_audit_event() creates an AuditEvent row."""
        event = record_audit_event(
            event_type="test_event",
            actor="test_actor",
            payload={"key": "value"},
            reason="testing",
            order_id=100,
        )
        self.assertIsNotNone(event.pk)
        self.assertEqual(event.event_type, "test_event")
        self.assertEqual(event.reason, "testing")
        self.assertEqual(AuditEvent.objects.filter(order_id=100).count(), 1)

    def test_record_audit_event_extracts_order_id_from_payload(self):
        """record_audit_event() extracts order_id and reason from payload if not explicitly passed."""
        event = record_audit_event(
            event_type="checkout_failed",
            actor="agent",
            payload={"order_id": 55, "detail": "Payment timeout"},
        )
        self.assertEqual(event.order_id, 55)
        self.assertEqual(event.reason, "Payment timeout")
        self.assertEqual(AuditEvent.objects.filter(order_id=55).count(), 1)

