from django.test import TestCase

from policy.engine import Decision, check_policy
from policy.models import PolicyRule


class PolicyEngineTests(TestCase):
    """Five deterministic tests — no mocking, no LLM, just ORM + engine."""

    def setUp(self):
        """Seed the three standard policy rules."""
        PolicyRule.objects.create(
            rule_type="spending_limit",
            scope="global",
            threshold_paise=1_500_000,
        )
        PolicyRule.objects.create(
            rule_type="max_single_order",
            scope="global",
            threshold_paise=800_000,
        )
        PolicyRule.objects.create(
            rule_type="category_approval",
            scope="global",
            threshold_paise=500_000,
            config={"category": "monitors"},
        )

    # ------------------------------------------------------------------
    # 1. ALLOW — total and all items under all thresholds
    # ------------------------------------------------------------------
    def test_allow_under_all_limits(self):
        """An order well under every threshold is ALLOW."""
        result = check_policy(
            user_id=1,
            proposed_order={
                "total_paise": 400_000,  # ₹4,000 — under ₹15,000 limit
                "items": [
                    {"category": "keyboards", "price_paise": 400_000},
                ],
            },
        )
        self.assertEqual(result.decision, Decision.ALLOW)
        self.assertEqual(result.rule_type, "none")

    # ------------------------------------------------------------------
    # 2. ALLOW at edge — total exactly equals spending_limit
    # ------------------------------------------------------------------
    def test_allow_at_exact_limit(self):
        """Total == threshold is not 'exceeds', so it's ALLOW."""
        result = check_policy(
            user_id=1,
            proposed_order={
                "total_paise": 1_500_000,  # exactly ₹15,000
                "items": [
                    {"category": "keyboards", "price_paise": 750_000},
                    {"category": "mice", "price_paise": 750_000},
                ],
            },
        )
        self.assertEqual(result.decision, Decision.ALLOW)

    # ------------------------------------------------------------------
    # 3. BLOCK — total exceeds spending_limit
    # ------------------------------------------------------------------
    def test_block_over_spending_limit(self):
        """Total over the spending limit triggers BLOCK."""
        result = check_policy(
            user_id=1,
            proposed_order={
                "total_paise": 1_600_000,  # ₹16,000 — over ₹15,000
                "items": [
                    {"category": "keyboards", "price_paise": 800_000},
                    {"category": "mice", "price_paise": 800_000},
                ],
            },
        )
        self.assertEqual(result.decision, Decision.BLOCK)
        self.assertEqual(result.rule_type, "spending_limit")
        self.assertIn("exceeds", result.reason.lower())

    # ------------------------------------------------------------------
    # 4. NEEDS_APPROVAL — single item over max_single_order
    # ------------------------------------------------------------------
    def test_needs_approval_single_item_over_max(self):
        """A single item priced above max_single_order triggers NEEDS_APPROVAL."""
        result = check_policy(
            user_id=1,
            proposed_order={
                "total_paise": 900_000,  # ₹9,000 — under spending limit
                "items": [
                    {"category": "keyboards", "price_paise": 900_000},  # over ₹8,000
                ],
            },
        )
        self.assertEqual(result.decision, Decision.NEEDS_APPROVAL)
        self.assertEqual(result.rule_type, "max_single_order")

    # ------------------------------------------------------------------
    # 5. NEEDS_APPROVAL — monitor category over threshold
    # ------------------------------------------------------------------
    def test_needs_approval_monitor_category(self):
        """A monitor item priced above category threshold triggers NEEDS_APPROVAL."""
        result = check_policy(
            user_id=1,
            proposed_order={
                "total_paise": 600_000,  # ₹6,000 — under spending limit
                "items": [
                    {"category": "monitors", "price_paise": 600_000},  # over ₹5,000
                ],
            },
        )
        self.assertEqual(result.decision, Decision.NEEDS_APPROVAL)
        self.assertEqual(result.rule_type, "category_approval")
        self.assertIn("monitors", result.reason.lower())
