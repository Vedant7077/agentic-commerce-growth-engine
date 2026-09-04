from django.db import models


class GrowthInsight(models.Model):
    INSIGHT_TYPE_CHOICES = [
        ("bundle_suggestion", "Bundle Suggestion"),
        ("underperforming_category", "Underperforming Category"),
    ]

    insight_type = models.CharField(max_length=50, choices=INSIGHT_TYPE_CHOICES)
    description = models.TextField()
    supporting_data = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"[{self.insight_type}] {self.description[:80]}"
