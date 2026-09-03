"""
Deterministic policy engine — zero LLM calls, zero langchain imports.

Evaluates active PolicyRule rows against a proposed order and returns
a PolicyResult with a decision (ALLOW / BLOCK / NEEDS_APPROVAL) and
a human-readable reason.
"""

from dataclasses import dataclass
from enum import Enum

from .models import PolicyRule


class Decision(Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    NEEDS_APPROVAL = "NEEDS_APPROVAL"


@dataclass
class PolicyResult:
    decision: Decision
    reason: str
    rule_type: str


def check_policy(user_id: int, proposed_order: dict) -> PolicyResult:
    """Evaluate all active policy rules against the proposed order.

    Args:
        user_id: The numeric user ID placing the order.
        proposed_order: Dict with keys:
            - total_paise (int): Total order value in paise.
            - items (list[dict]): Each dict has 'category' (str)
              and 'price_paise' (int).

    Returns:
        PolicyResult with the first triggered rule, or ALLOW if none match.
    """
    total_paise: int = proposed_order["total_paise"]
    items: list[dict] = proposed_order.get("items", [])

    # Fetch all active rules that apply to this user (global + user-specific).
    rules = PolicyRule.objects.filter(
        active=True,
        scope__in=["global", str(user_id)],
    )

    # --- 1. Spending limit (BLOCK) ---
    for rule in rules.filter(rule_type="spending_limit"):
        if total_paise > rule.threshold_paise:
            return PolicyResult(
                decision=Decision.BLOCK,
                reason=(
                    f"Order total ₹{total_paise / 100:.2f} exceeds "
                    f"spending limit ₹{rule.threshold_paise / 100:.2f}"
                ),
                rule_type="spending_limit",
            )

    # --- 2. Max single order (NEEDS_APPROVAL) ---
    for rule in rules.filter(rule_type="max_single_order"):
        for item in items:
            if item.get("price_paise", 0) > rule.threshold_paise:
                return PolicyResult(
                    decision=Decision.NEEDS_APPROVAL,
                    reason=(
                        f"Item priced at ₹{item['price_paise'] / 100:.2f} "
                        f"exceeds single-order limit "
                        f"₹{rule.threshold_paise / 100:.2f}"
                    ),
                    rule_type="max_single_order",
                )

    # --- 3. Category approval (NEEDS_APPROVAL) ---
    for rule in rules.filter(rule_type="category_approval"):
        required_category = rule.config.get("category", "")
        for item in items:
            if (
                item.get("category", "").lower() == required_category.lower()
                and item.get("price_paise", 0) > rule.threshold_paise
            ):
                return PolicyResult(
                    decision=Decision.NEEDS_APPROVAL,
                    reason=(
                        f"Item in category '{required_category}' priced at "
                        f"₹{item['price_paise'] / 100:.2f} exceeds "
                        f"category threshold "
                        f"₹{rule.threshold_paise / 100:.2f}"
                    ),
                    rule_type="category_approval",
                )

    # --- All clear ---
    return PolicyResult(
        decision=Decision.ALLOW,
        reason="Order passes all policy checks",
        rule_type="none",
    )
