from django.db import models


class Product(models.Model):
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=100)
    price_paise = models.IntegerField(
        help_text="Price in paise (1 INR = 100 paise)"
    )
    rating = models.FloatField(default=0.0)
    stock = models.IntegerField(default=0)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        # pyrefly: ignore [unsupported-operation]
        price_inr = self.price_paise / 100
        return f"{self.name} (₹{price_inr:.2f})"
