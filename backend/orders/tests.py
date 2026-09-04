from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from audit.models import AuditEvent
from catalogue.models import Product
from .models import Cart, CartItem, Order, OrderItem


class CartTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create(
            name="Test User", email="test@example.com", spending_limit_paise=1000000
        )
        self.product = Product.objects.create(
            name="Test Keyboard",
            category="keyboards",
            price_paise=500000,
            rating=4.5,
            stock=10,
            description="A test keyboard for programming.",
        )

    def test_add_item_to_cart(self):
        """POST /cart/items/ creates a CartItem and a Cart if none exists."""
        response = self.client.post(
            "/cart/items/",
            {"user_id": self.user.pk, "product_id": self.product.pk, "quantity": 2},
            format="json",
        )
        self.assertEqual(response.status_code, 201)

        # Cart and CartItem exist
        self.assertEqual(Cart.objects.filter(user=self.user).count(), 1)
        cart = Cart.objects.get(user=self.user)
        self.assertEqual(cart.items.count(), 1)
        self.assertEqual(cart.items.first().quantity, 2)

    def test_add_item_increments_quantity(self):
        """Adding the same product again increments quantity."""
        payload = {
            "user_id": self.user.pk,
            "product_id": self.product.pk,
            "quantity": 1,
        }
        self.client.post("/cart/items/", payload, format="json")
        self.client.post("/cart/items/", payload, format="json")

        cart = Cart.objects.get(user=self.user)
        self.assertEqual(cart.items.first().quantity, 2)

    def test_add_item_creates_audit_event(self):
        """Adding an item to the cart creates a cart_item_added audit event."""
        self.client.post(
            "/cart/items/",
            {"user_id": self.user.pk, "product_id": self.product.pk, "quantity": 1},
            format="json",
        )
        events = AuditEvent.objects.filter(event_type="cart_item_added")
        self.assertEqual(events.count(), 1)
        self.assertEqual(events.first().actor, self.user.email)


class OrderTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create(
            name="Order User", email="order@example.com", spending_limit_paise=5000000
        )
        self.product_a = Product.objects.create(
            name="Product A",
            category="keyboards",
            price_paise=300000,
            rating=4.0,
            stock=20,
            description="Product A description.",
        )
        self.product_b = Product.objects.create(
            name="Product B",
            category="mice",
            price_paise=150000,
            rating=4.2,
            stock=15,
            description="Product B description.",
        )
        # Add items to cart
        self.client.post(
            "/cart/items/",
            {"user_id": self.user.pk, "product_id": self.product_a.pk, "quantity": 2},
            format="json",
        )
        self.client.post(
            "/cart/items/",
            {"user_id": self.user.pk, "product_id": self.product_b.pk, "quantity": 1},
            format="json",
        )

    def test_create_order_from_cart(self):
        """POST /orders/ creates an Order with correct total and OrderItems."""
        response = self.client.post(
            "/orders/", {"user_id": self.user.pk}, format="json"
        )
        self.assertEqual(response.status_code, 201)

        # Order exists
        self.assertEqual(Order.objects.filter(user=self.user).count(), 1)
        order = Order.objects.get(user=self.user)
        self.assertEqual(order.status, "pending")

        # OrderItems
        self.assertEqual(order.items.count(), 2)

        # Total = (300000 * 2) + (150000 * 1) = 750000
        self.assertEqual(order.total_paise, 750000)

    def test_order_snapshots_price(self):
        """OrderItem.price_paise_at_purchase matches the product's price at order time."""
        self.client.post("/orders/", {"user_id": self.user.pk}, format="json")
        order = Order.objects.get(user=self.user)

        item_a = order.items.get(product=self.product_a)
        self.assertEqual(item_a.price_paise_at_purchase, 300000)

        item_b = order.items.get(product=self.product_b)
        self.assertEqual(item_b.price_paise_at_purchase, 150000)

    def test_order_clears_cart(self):
        """After creating an order, the cart items are cleared."""
        self.client.post("/orders/", {"user_id": self.user.pk}, format="json")
        cart = Cart.objects.get(user=self.user)
        self.assertEqual(cart.items.count(), 0)

    def test_create_order_creates_audit_event(self):
        """Creating an order creates an order_created audit event with order_id."""
        self.client.post("/orders/", {"user_id": self.user.pk}, format="json")
        order = Order.objects.get(user=self.user)

        events = AuditEvent.objects.filter(
            event_type="order_created", order_id=order.pk
        )
        self.assertEqual(events.count(), 1)
        self.assertEqual(events.first().actor, self.user.email)


class IdempotencyTests(TestCase):
    """Test that idempotency keys prevent duplicate order creation."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create(
            name="Idemp User", email="idemp@example.com", spending_limit_paise=5000000
        )
        self.product = Product.objects.create(
            name="Idemp Product",
            category="keyboards",
            price_paise=200000,
            rating=4.0,
            stock=10,
            description="A product for idempotency testing.",
        )

    def _add_to_cart(self):
        """Helper: add a product to the user's cart."""
        self.client.post(
            "/cart/items/",
            {"user_id": self.user.pk, "product_id": self.product.pk, "quantity": 1},
            format="json",
        )

    def test_same_idempotency_key_returns_existing_order(self):
        """Submitting the same idempotency_key twice returns the same order, not a duplicate."""
        self._add_to_cart()
        key = "idemp-abc-123"

        # First call — creates the order
        resp1 = self.client.post(
            "/orders/",
            {"user_id": self.user.pk, "idempotency_key": key},
            format="json",
        )
        self.assertIn(resp1.status_code, (200, 201))
        order_id_1 = resp1.data["id"]

        # Re-add item so the "cart is empty" guard doesn't block the second call
        self._add_to_cart()

        # Second call — same key, should return existing order
        resp2 = self.client.post(
            "/orders/",
            {"user_id": self.user.pk, "idempotency_key": key},
            format="json",
        )
        self.assertEqual(resp2.status_code, 200)
        order_id_2 = resp2.data["id"]

        # Same order PK returned
        self.assertEqual(order_id_1, order_id_2)

        # Only one Order exists in DB with this key
        self.assertEqual(Order.objects.filter(idempotency_key=key).count(), 1)

    def test_different_keys_create_separate_orders(self):
        """Two different idempotency keys produce two distinct orders."""
        self._add_to_cart()
        resp1 = self.client.post(
            "/orders/",
            {"user_id": self.user.pk, "idempotency_key": "key-alpha"},
            format="json",
        )
        self.assertIn(resp1.status_code, (200, 201))

        # Re-add item
        self._add_to_cart()

        resp2 = self.client.post(
            "/orders/",
            {"user_id": self.user.pk, "idempotency_key": "key-beta"},
            format="json",
        )
        self.assertIn(resp2.status_code, (200, 201))

        self.assertNotEqual(resp1.data["id"], resp2.data["id"])
        self.assertEqual(Order.objects.count(), 2)

    def test_out_of_stock_product_returns_error(self):
        """Ordering a product with stock=0 returns an error without crashing."""
        self._add_to_cart()
        # Set stock to 0
        self.product.stock = 0
        self.product.save()

        resp = self.client.post(
            "/orders/",
            {"user_id": self.user.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("out of stock", resp.data["detail"])

        # Audit event recorded
        self.assertTrue(
            AuditEvent.objects.filter(event_type="product_unavailable_failed").exists()
        )

