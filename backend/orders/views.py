import uuid

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from accounts.models import User
from catalogue.models import Product
from audit.services import record_audit_event
from .models import Cart, CartItem, Order, OrderItem
from .serializers import (
    AddCartItemSerializer,
    CartReadSerializer,
    CreateOrderSerializer,
    OrderReadSerializer,
)


@api_view(["POST"])
def add_cart_item(request):
    """
    POST /cart/items/
    Body: { "user_id": int, "product_id": int, "quantity": int }
    """
    serializer = AddCartItemSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    user_id = serializer.validated_data["user_id"]
    product_id = serializer.validated_data["product_id"]
    quantity = serializer.validated_data["quantity"]

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return Response(
            {"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND
        )

    try:
        product = Product.objects.get(pk=product_id)
    except Product.DoesNotExist:
        return Response(
            {"detail": "Product not found."}, status=status.HTTP_404_NOT_FOUND
        )

    cart, _ = Cart.objects.get_or_create(user=user)
    cart_item, created = CartItem.objects.get_or_create(
        cart=cart, product=product, defaults={"quantity": quantity}
    )
    if not created:
        cart_item.quantity += quantity
        cart_item.save()

    # Audit
    record_audit_event(
        event_type="cart_item_added",
        actor=user.email,
        payload={
            "cart_id": cart.pk,
            "product_id": product.pk,
            "product_name": product.name,
            "quantity_added": quantity,
            "new_quantity": cart_item.quantity,
        },
    )

    cart.refresh_from_db()
    return Response(
        CartReadSerializer(cart).data, status=status.HTTP_201_CREATED
    )


@api_view(["GET"])
def get_cart(request):
    """
    GET /cart/?user_id=<int>
    """
    user_id = request.query_params.get("user_id")
    if not user_id:
        return Response(
            {"detail": "user_id query param is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        cart = Cart.objects.prefetch_related("items__product").get(
            user_id=int(user_id)
        )
    except Cart.DoesNotExist:
        return Response(
            {"detail": "Cart not found."}, status=status.HTTP_404_NOT_FOUND
        )

    return Response(CartReadSerializer(cart).data)


@api_view(["POST"])
def create_order(request):
    """
    POST /orders/
    Body: { "user_id": int }
    Creates an Order + OrderItems from the user's current cart,
    snapshotting price_paise_at_purchase from each product's current price.
    """
    serializer = CreateOrderSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    user_id = serializer.validated_data["user_id"]

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return Response(
            {"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND
        )

    try:
        cart = Cart.objects.prefetch_related("items__product").get(user=user)
    except Cart.DoesNotExist:
        return Response(
            {"detail": "No cart found for this user."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    cart_items = cart.items.select_related("product").all()
    if not cart_items.exists():
        return Response(
            {"detail": "Cart is empty."}, status=status.HTTP_400_BAD_REQUEST
        )

    # Create order
    order = Order.objects.create(
        user=user,
        idempotency_key=str(uuid.uuid4()),
        status="pending",
    )

    total = 0
    order_items = []
    for ci in cart_items:
        price_snapshot = ci.product.price_paise
        order_items.append(
            OrderItem(
                order=order,
                product=ci.product,
                quantity=ci.quantity,
                price_paise_at_purchase=price_snapshot,
            )
        )
        total += price_snapshot * ci.quantity

    OrderItem.objects.bulk_create(order_items)
    order.total_paise = total
    order.save(update_fields=["total_paise"])

    # Clear cart
    cart_items.delete()

    # Audit
    record_audit_event(
        event_type="order_created",
        actor=user.email,
        payload={
            "order_id": order.pk,
            "total_paise": total,
            "item_count": sum(item.quantity for item in order_items),
        },
        order_id=order.pk,
    )

    order.refresh_from_db()
    return Response(
        OrderReadSerializer(order).data, status=status.HTTP_201_CREATED
    )
