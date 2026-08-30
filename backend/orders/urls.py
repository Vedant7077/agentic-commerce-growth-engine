from django.urls import path

from . import views

urlpatterns = [
    path("cart/items/", views.add_cart_item, name="cart-add-item"),
    path("cart/", views.get_cart, name="cart-detail"),
    path("orders/", views.create_order, name="order-create"),
]
