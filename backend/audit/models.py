from django.db import models


class AuditEvent(models.Model):
    event_type = models.CharField(max_length=100)
    actor = models.CharField(max_length=255)
    payload = models.JSONField(default=dict)
    reason = models.TextField(null=True, blank=True)
    order_id = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"[{self.event_type}] by {self.actor} at {self.created_at}"
