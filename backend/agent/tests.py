"""
Unit tests for agent.scoring — pure Python, no Django or mocking needed.

Run with:
    python -m pytest agent/tests.py -v
    # or
    python -m unittest agent.tests -v
"""

import unittest

from agent.scoring import score_product, score_product_detailed


class TestScoreProduct(unittest.TestCase):
    """Tests for score_product covering clear winner, tie-breaker,
    over-budget, and best-value sweet-spot scenarios."""

    # ── helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _make_product(price_paise, rating, description=""):
        return {
            "id": 1,
            "name": "Test Product",
            "price_paise": price_paise,
            "rating": rating,
            "description": description,
        }

    @staticmethod
    def _make_requirements(max_price, min_rating=0.0, features=None):
        return {
            "category": "keyboards",
            "max_price": max_price,
            "min_rating": min_rating,
            "required_features": features or [],
        }

    # ── 1. clear winner ──────────────────────────────────────────────

    def test_clear_winner(self):
        """A well-priced, high-rated product with matching features beats
        an over-budget product decisively."""
        reqs = self._make_requirements(
            max_price=500_000,
            features=["mechanical", "rgb"],
        )
        good = self._make_product(
            price_paise=375_000,   # 75 % of budget — sweet spot
            rating=4.5,
            description="Mechanical keyboard with RGB backlighting",
        )
        bad = self._make_product(
            price_paise=600_000,   # over budget
            rating=4.8,
            description="Mechanical keyboard with RGB and more",
        )
        self.assertGreater(score_product(good, reqs), score_product(bad, reqs))

    # ── 2. tie-breaker via feature overlap ───────────────────────────

    def test_tiebreaker_feature_overlap(self):
        """Two products at the same price and rating; the one with better
        feature overlap wins."""
        reqs = self._make_requirements(
            max_price=400_000,
            features=["mechanical", "wireless", "hot swappable"],
        )
        better_features = self._make_product(
            price_paise=300_000,
            rating=4.0,
            description="Wireless mechanical keyboard, hot swappable switches",
        )
        worse_features = self._make_product(
            price_paise=300_000,
            rating=4.0,
            description="Mechanical keyboard with wired connection",
        )
        self.assertGreater(
            score_product(better_features, reqs),
            score_product(worse_features, reqs),
        )

    # ── 3. over-budget ───────────────────────────────────────────────

    def test_over_budget_zero_price_score(self):
        """A product priced above max_price gets 0 for the price component."""
        reqs = self._make_requirements(max_price=200_000)
        over = self._make_product(price_paise=250_000, rating=5.0)

        total, components = score_product_detailed(over, reqs)
        self.assertEqual(components["price_fit"], 0.0)
        # Total should be rating + features only (no price contribution)
        # rating = 5/5 = 1.0 → 0.35; features empty → 1.0 → 0.25 = 0.60
        self.assertAlmostEqual(total, 0.35 * 1.0 + 0.25 * 1.0, places=4)

    # ── 4. best-value sweet spot ─────────────────────────────────────

    def test_sweet_spot_beats_cheapest(self):
        """A product at ~75 % of budget scores higher on price-fit than
        one at ~20 % of budget, validating 'best value not cheapest'."""
        reqs = self._make_requirements(max_price=1_000_000)

        sweet = self._make_product(price_paise=750_000, rating=4.0)
        cheapest = self._make_product(price_paise=200_000, rating=4.0)

        _, sweet_comp = score_product_detailed(sweet, reqs)
        _, cheap_comp = score_product_detailed(cheapest, reqs)

        self.assertGreater(sweet_comp["price_fit"], cheap_comp["price_fit"])


from unittest.mock import patch, MagicMock
from django.test import TestCase as DjangoTestCase
from langchain_core.messages import HumanMessage
from audit.models import AuditEvent
from agent.graph import extract_requirements


class TestExtractRequirementsMalformedResponse(DjangoTestCase):
    """Test that extract_requirements handles malformed AI responses by logging audit events and retrying."""

    @patch("agent.graph._extraction_model")
    def test_malformed_ai_response_triggers_audit_and_retry(self, mock_model):
        mock_structured = MagicMock()
        mock_structured.invoke.side_effect = [
            Exception("Invalid JSON: Unparseable LLM output"),
            {"category": "keyboards", "max_price": 500000, "min_rating": 4.0, "required_features": []},
        ]
        mock_model.with_structured_output.return_value = mock_structured

        state = {
            "messages": [HumanMessage(content="Find me a keyboard under 5000")],
            "request_id": "test-req-malformed-1",
        }

        result = extract_requirements(state)

        self.assertEqual(result["requirements"]["category"], "keyboards")

        events = AuditEvent.objects.filter(event_type="malformed_ai_response")
        self.assertEqual(events.count(), 1)
        self.assertEqual(events.first().payload["attempt"], 1)

    @patch("agent.graph._extraction_model")
    def test_malformed_ai_response_both_fail_falls_back_to_empty(self, mock_model):
        mock_structured = MagicMock()
        mock_structured.invoke.side_effect = [
            Exception("Fail 1"),
            Exception("Fail 2"),
        ]
        mock_model.with_structured_output.return_value = mock_structured

        state = {
            "messages": [HumanMessage(content="Find me a keyboard")],
            "request_id": "test-req-malformed-2",
        }

        result = extract_requirements(state)

        self.assertIsNone(result["requirements"]["category"])

        events = AuditEvent.objects.filter(event_type="malformed_ai_response")
        self.assertEqual(events.count(), 2)


from accounts.models import User
from catalogue.models import Product
from orders.models import Cart, CartItem, Order
from agent.tools import create_order


class TestCreateOrderToolIdempotency(DjangoTestCase):
    """Test that create_order LangGraph tool enforces idempotency."""

    def setUp(self):
        self.user = User.objects.create(
            name="Idemp User", email="idemp_agent@example.com", spending_limit_paise=5000000
        )
        self.product = Product.objects.create(
            name="Idemp Mouse",
            category="mice",
            price_paise=150000,
            rating=4.5,
            stock=10,
            description="A mouse for idempotency test.",
        )
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1)

    @patch("payments.services.create_razorpay_order")
    def test_create_order_same_idempotency_key_returns_existing(self, mock_create_rzp):
        """Replaying create_order with the same idempotency_key returns existing order without re-calling Razorpay."""
        mock_create_rzp.return_value = {"id": "order_rzp_mock_123"}
        key = "idemp-key-agent-001"

        # First call creates order and invokes create_razorpay_order
        res1 = create_order.invoke({"user_id": self.user.pk, "idempotency_key": key})
        self.assertEqual(res1["status"], "confirmed")
        self.assertEqual(mock_create_rzp.call_count, 1)
        first_order_id = res1["id"]

        # Second call with the same key returns the existing order without calling Razorpay again
        res2 = create_order.invoke({"user_id": self.user.pk, "idempotency_key": key})
        self.assertEqual(res2["id"], first_order_id)
        self.assertEqual(mock_create_rzp.call_count, 1)  # NOT called again
        self.assertEqual(Order.objects.filter(idempotency_key=key).count(), 1)


if __name__ == "__main__":
    unittest.main()


