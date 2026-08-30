from django.db import models

from accounts.models import User
from catalogue.models import Product


class Cart(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="carts")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Cart #{self.pk} for {self.user.name}"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=1)

    class Meta:
        unique_together = ("cart", "product")

    def __str__(self):
        return f"{self.quantity}× {self.product.name}"


class Order(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("confirmed", "Confirmed"),
        ("paid", "Paid"),
        ("failed", "Failed"),
        ("blocked", "Blocked"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="orders")
    total_paise = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    razorpay_order_id = models.CharField(max_length=255, null=True, blank=True)
    idempotency_key = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order #{self.pk} — {self.status}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=1)
    price_paise_at_purchase = models.IntegerField()

    def __str__(self):
        return f"{self.quantity}× {self.product.name} @ ₹{self.price_paise_at_purchase / 100:.2f}"
