from django.db import models


class PolicyRule(models.Model):
    RULE_TYPE_CHOICES = [
        ("spending_limit", "Spending Limit"),
        ("max_single_order", "Max Single Order"),
        ("category_approval", "Category Approval"),
    ]

    rule_type = models.CharField(max_length=30, choices=RULE_TYPE_CHOICES)
    scope = models.CharField(
        max_length=50,
        default="global",
        help_text='\"global\" or a specific user_id as a string',
    )
    threshold_paise = models.IntegerField(
        help_text="Threshold in paise (1 INR = 100 paise)",
    )
    config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Extra parameters (e.g. category name)",
    )
    active = models.BooleanField(default=True)

    objects = models.Manager()

    class Meta:
        ordering = ["rule_type"]

    def __str__(self) -> str:
        # pyrefly: ignore [unsupported-operation]
        return f"{self.rule_type} ({self.scope}) — ₹{self.threshold_paise / 100:.2f}"
