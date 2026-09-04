from django.core.exceptions import ObjectDoesNotExist
from django.db import models

from accounts.models import User
from catalogue.models import Product


class Cart(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="carts"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()

    class DoesNotExist(ObjectDoesNotExist):
        pass

    def __str__(self) -> str:
        return f"Cart #{self.pk} for {self.user.name}"


class CartItem(models.Model):
    cart = models.ForeignKey(
        Cart, on_delete=models.CASCADE, related_name="items"
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=1)

    objects = models.Manager()

    class Meta:
        unique_together = ("cart", "product")

    def __str__(self) -> str:
        return f"{self.quantity}× {self.product.name}"


class Order(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("confirmed", "Confirmed"),
        ("paid", "Paid"),
        ("failed", "Failed"),
        ("blocked", "Blocked"),
    ]

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="orders"
    )
    total_paise = models.IntegerField(default=0)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending"
    )
    razorpay_order_id = models.CharField(max_length=255, null=True, blank=True)
    idempotency_key = models.CharField(max_length=255, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()

    class DoesNotExist(ObjectDoesNotExist):
        pass

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Order #{self.pk} — {self.status}"


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="items"
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=1)
    price_paise_at_purchase = models.IntegerField()

    objects = models.Manager()

    def __str__(self) -> str:
        # pyrefly: ignore [unsupported-operation]
        price_inr = self.price_paise_at_purchase / 100
        return f"{self.quantity}× {self.product.name} @ ₹{price_inr:.2f}"
