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


if __name__ == "__main__":
    unittest.main()
