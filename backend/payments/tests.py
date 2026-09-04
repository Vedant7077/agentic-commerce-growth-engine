import uuid
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings

from accounts.models import User
from catalogue.models import Product
from orders.models import Cart, CartItem, Order, OrderItem
from audit.models import AuditEvent
from payments.services import (
    create_razorpay_order,
    handle_razorpay_timeout,
    RazorpayTimeoutError,
)


class RazorpayTimeoutTests(TestCase):
    """Test Razorpay timeout simulation and check-before-retry recovery."""

    def setUp(self):
        self.user = User.objects.create(
            name="Timeout User",
            email="timeout@example.com",
            spending_limit_paise=5000000,
        )
        self.product = Product.objects.create(
            name="Timeout Product",
            category="keyboards",
            price_paise=300000,
            rating=4.0,
            stock=10,
            description="A product for timeout testing.",
        )
        self.order = Order.objects.create(
            user=self.user,
            idempotency_key=str(uuid.uuid4()),
            total_paise=300000,
            status="pending",
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=1,
            price_paise_at_purchase=300000,
        )

    @patch.dict("os.environ", {"FORCE_TIMEOUT": "true", "RAZORPAY_KEY_ID": "rzp_test_x", "RAZORPAY_KEY_SECRET": "secret"})
    def test_force_timeout_raises_error(self):
        """When FORCE_TIMEOUT=true, create_razorpay_order raises RazorpayTimeoutError."""
        with self.assertRaises(RazorpayTimeoutError) as ctx:
            create_razorpay_order(self.order)
        self.assertIn("FORCE_TIMEOUT", str(ctx.exception))

    @patch.dict("os.environ", {"FORCE_TIMEOUT": "false", "RAZORPAY_KEY_ID": "rzp_test_x", "RAZORPAY_KEY_SECRET": "secret"})
    @patch("payments.services._get_razorpay_client")
    def test_create_razorpay_order_payment_failure(self, mock_get_client):
        """When Razorpay API rejects order creation, error is raised and order remains unconfirmed."""
        import razorpay
        mock_client = MagicMock()
        mock_client.order.create.side_effect = razorpay.errors.BadRequestError("Invalid amount")
        mock_get_client.return_value = mock_client

        with self.assertRaises(razorpay.errors.BadRequestError):
            create_razorpay_order(self.order)

        self.order.refresh_from_db()
        self.assertNotEqual(self.order.status, "confirmed")


    @patch.dict("os.environ", {"RAZORPAY_KEY_ID": "rzp_test_x", "RAZORPAY_KEY_SECRET": "secret"})
    @patch("payments.services._get_razorpay_client")
    def test_handle_timeout_fetches_existing_order(self, mock_get_client):
        """When order has a razorpay_order_id, recovery fetches it and confirms."""
        self.order.razorpay_order_id = "order_test_existing123"
        self.order.save()

        mock_client = MagicMock()
        mock_client.order.fetch.return_value = {
            "id": "order_test_existing123",
            "amount": 300000,
            "status": "created",
        }
        mock_get_client.return_value = mock_client

        result = handle_razorpay_timeout(self.order)

        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "order_test_existing123")

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "confirmed")

        # Audit event recorded
        self.assertTrue(
            AuditEvent.objects.filter(event_type="razorpay_timeout_recovered").exists()
        )

    @patch.dict("os.environ", {"FORCE_TIMEOUT": "false", "RAZORPAY_KEY_ID": "rzp_test_x", "RAZORPAY_KEY_SECRET": "secret"})
    @patch("payments.services._get_razorpay_client")
    def test_handle_timeout_retries_when_no_rzp_id(self, mock_get_client):
        """When order has no razorpay_order_id, recovery retries and succeeds."""
        # Ensure no razorpay_order_id
        self.order.razorpay_order_id = None
        self.order.save()

        mock_client = MagicMock()
        mock_client.order.create.return_value = {
            "id": "order_test_retry456",
            "amount": 300000,
            "status": "created",
        }
        mock_get_client.return_value = mock_client

        result = handle_razorpay_timeout(self.order)

        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "order_test_retry456")

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "confirmed")
        self.assertEqual(self.order.razorpay_order_id, "order_test_retry456")

        # Audit event recorded
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="razorpay_timeout_recovered",
                payload__recovery="retried_successfully",
            ).exists()
        )

    @patch.dict("os.environ", {"RAZORPAY_KEY_ID": "rzp_test_x", "RAZORPAY_KEY_SECRET": "secret"})
    @patch("payments.services._get_razorpay_client")
    def test_handle_timeout_marks_failed_when_fetch_fails(self, mock_get_client):
        """When fetch fails, order is marked as failed."""
        self.order.razorpay_order_id = "order_test_ghost789"
        self.order.save()

        mock_client = MagicMock()
        mock_client.order.fetch.side_effect = Exception("Order not found on Razorpay")
        mock_get_client.return_value = mock_client

        result = handle_razorpay_timeout(self.order)

        self.assertIsNone(result)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "failed")

        # Audit event recorded
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="razorpay_timeout_failed",
                payload__recovery="fetch_failed",
            ).exists()
        )
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="payment_timeout_handled",
                actor="system",
                reason="Razorpay timeout after retry",
                order_id=self.order.pk,
            ).exists()
        )

    @patch.dict("os.environ", {"RAZORPAY_KEY_ID": "rzp_test_x", "RAZORPAY_KEY_SECRET": "secret"})
    @patch("payments.services._get_razorpay_client")
    def test_handle_timeout_marks_failed_when_retry_fails(self, mock_get_client):
        """When retry fails, order is marked failed and payment_timeout_handled event is created."""
        self.order.razorpay_order_id = None
        self.order.save()

        mock_client = MagicMock()
        mock_client.order.create.side_effect = Exception("Simulated retry timeout")
        mock_get_client.return_value = mock_client

        result = handle_razorpay_timeout(self.order)

        self.assertIsNone(result)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "failed")

        # Audit events recorded
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="razorpay_timeout_failed",
                payload__recovery="retry_failed",
            ).exists()
        )
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="payment_timeout_handled",
                actor="system",
                reason="Razorpay timeout after retry",
                order_id=self.order.pk,
            ).exists()
        )

