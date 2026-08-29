from django.db import models


class Product(models.Model):
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=100)
    price_paise = models.IntegerField(help_text="Price in paise (1 INR = 100 paise)")
    rating = models.FloatField(default=0.0)
    stock = models.IntegerField(default=0)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} (₹{self.price_paise / 100:.2f})"
