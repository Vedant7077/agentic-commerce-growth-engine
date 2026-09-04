"""
LangChain tools for the product catalogue agent.

Each tool calls the Django REST API over HTTP using httpx,
so the Django dev server must be running for the agent to work.
"""

import httpx
from langchain_core.tools import tool

import os

BASE_URL = os.environ.get("DJANGO_BASE_URL", "http://127.0.0.1:8000")


@tool
def search_catalogue(
    query: str,
    category: str | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
) -> list[dict]:
    """Search the product catalogue.

    Args:
        query: Free-text search term (matched against product name and description).
        category: Optional category filter (e.g. "keyboards", "mice").
        min_price: Optional minimum price filter **in paise** (1 INR = 100 paise).
                   For example, ₹1,000 = 100000 paise.
        max_price: Optional maximum price filter **in paise** (1 INR = 100 paise).
                   For example, ₹5,000 = 500000 paise.

    Returns:
        A list of matching product dicts from the catalogue API.
    """
    params: dict = {"q": query}
    if category is not None:
        params["category"] = category
    if min_price is not None:
        params["min_price"] = min_price
    if max_price is not None:
        params["max_price"] = max_price

    response = httpx.get(f"{BASE_URL}/products/", params=params)
    response.raise_for_status()
    return response.json()


@tool
def get_product_details(product_id: int) -> dict:
    """Get full details for a single product by its ID.

    Args:
        product_id: The numeric ID of the product.

    Returns:
        A dict with the product's full details from the catalogue API.
    """
    response = httpx.get(f"{BASE_URL}/products/{product_id}/")
    response.raise_for_status()
    return response.json()


@tool
def compare_products(product_ids: list[int]) -> list[dict]:
    """Retrieve details for multiple products so they can be compared side-by-side.

    Args:
        product_ids: A list of product IDs to compare.

    Returns:
        A list of product detail dicts, one per requested ID.
    """
    products = []
    for pid in product_ids:
        response = httpx.get(f"{BASE_URL}/products/{pid}/")
        response.raise_for_status()
        products.append(response.json())
    return products


@tool
def add_to_cart(user_id: int, product_id: int, quantity: int = 1) -> dict:
    """Add a product to the user's cart.

    Args:
        user_id: The numeric ID of the user.
        product_id: The numeric ID of the product to add.
        quantity: Number of units to add (default 1).

    Returns:
        The updated cart dict from the orders API.
    """
    response = httpx.post(
        f"{BASE_URL}/cart/items/",
        json={"user_id": user_id, "product_id": product_id, "quantity": quantity},
    )
    response.raise_for_status()
    return response.json()


@tool
def create_order(
    user_id: int,
    idempotency_key: str | None = None,
    request_id: str | None = None,
) -> dict:
    """Create an order from the user's current cart and generate a Razorpay payment order.

    This converts the user's cart into a Django Order with OrderItems,
    then invokes the Razorpay SDK to create a corresponding payment order.
    Uses an idempotency key to prevent duplicate orders on retry.

    Args:
        user_id: The numeric ID of the user whose cart should be converted to an order.
        idempotency_key: Optional unique key for idempotent order creation.
        request_id: Optional correlation ID for tracing and audit logging.

    Returns:
        A dict with the Django order details including the razorpay_order_id.
    """
    import uuid
    from accounts.models import User
    from catalogue.models import Product
    from orders.models import Cart, Order, OrderItem
    from payments.services import (
        create_razorpay_order,
        handle_razorpay_timeout,
        RazorpayTimeoutError,
    )
    from audit.services import record_audit_event

    # Generate idempotency key if not provided
    idem_key = idempotency_key or str(uuid.uuid4())

    # --- Idempotency check: return existing order if key matches ---
    existing_order = Order.objects.filter(idempotency_key=idem_key).first()
    if existing_order:
        return {
            "id": existing_order.pk,
            "status": existing_order.status,
            "total_paise": existing_order.total_paise,
            "razorpay_order_id": existing_order.razorpay_order_id or "",
        }

    # Look up user
    user = User.objects.get(pk=user_id)

    # Look up cart
    cart = Cart.objects.prefetch_related("items__product").get(user=user)
    cart_items = cart.items.select_related("product").all()
    if not cart_items.exists():
        return {"status": "error", "detail": "Cart is empty."}

    # --- Product availability check ---
    for ci in cart_items:
        try:
            product = Product.objects.get(pk=ci.product_id)
        except Product.DoesNotExist:
            record_audit_event(
                event_type="product_unavailable_failed",
                actor="agent",
                payload={
                    "user_id": user_id,
                    "product_id": ci.product_id,
                    "reason": "Product no longer exists",
                },
            )
            return {
                "status": "error",
                "detail": f"Product {ci.product_id} no longer exists.",
            }
        if product.stock <= 0:
            record_audit_event(
                event_type="product_unavailable_failed",
                actor="agent",
                payload={
                    "user_id": user_id,
                    "product_id": product.pk,
                    "product_name": product.name,
                    "reason": "Product out of stock",
                },
            )
            return {
                "status": "error",
                "detail": f"Product '{product.name}' is out of stock.",
            }

    # Create the Django order
    order = Order.objects.create(
        user=user,
        idempotency_key=idem_key,
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

    # Create a Razorpay order for payment (with timeout handling)
    try:
        rzp_order = create_razorpay_order(order)
    except RazorpayTimeoutError:
        record_audit_event(
            event_type="razorpay_timeout",
            actor="system",
            payload={
                "request_id": request_id,
                "order_id": order.pk,
                "user_id": user_id,
                "total_paise": total,
            },
            order_id=order.pk,
        )
        # Attempt recovery: check before retry
        rzp_order = handle_razorpay_timeout(order, request_id=request_id)
        if rzp_order is None:
            return {
                "id": order.pk,
                "status": "failed",
                "total_paise": order.total_paise,
                "razorpay_order_id": "",
                "detail": "Razorpay timeout — recovery failed.",
            }

    return {
        "id": order.pk,
        "status": "confirmed",
        "total_paise": order.total_paise,
        "razorpay_order_id": rzp_order["id"],
    }
