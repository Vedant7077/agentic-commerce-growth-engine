from rest_framework import serializers

from accounts.models import User
from catalogue.models import Product
from catalogue.serializers import ProductSerializer
from .models import Cart, CartItem, Order, OrderItem


# ── Cart ───────────────────────────────────────────────────────────────────

class AddCartItemSerializer(serializers.Serializer):
    """Write serializer for POST /cart/items/"""
    user_id = serializers.IntegerField()
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, default=1)


class CartItemReadSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)

    class Meta:
        model = CartItem
        fields = ("id", "product", "quantity")


class CartReadSerializer(serializers.ModelSerializer):
    items = CartItemReadSerializer(many=True, read_only=True)

    class Meta:
        model = Cart
        fields = ("id", "user", "items", "created_at")


# ── Order ──────────────────────────────────────────────────────────────────

class OrderItemReadSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)

    class Meta:
        model = OrderItem
        fields = ("id", "product", "quantity", "price_paise_at_purchase")


class OrderReadSerializer(serializers.ModelSerializer):
    items = OrderItemReadSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = (
            "id", "user", "total_paise", "status",
            "razorpay_order_id", "idempotency_key", "items", "created_at",
        )


class CreateOrderSerializer(serializers.Serializer):
    """Write serializer for POST /orders/"""
    user_id = serializers.IntegerField()
    idempotency_key = serializers.CharField(max_length=255, required=False, default=None)
