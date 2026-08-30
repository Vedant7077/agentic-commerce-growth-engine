from django.db import models


class User(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    spending_limit_paise = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.email})"
