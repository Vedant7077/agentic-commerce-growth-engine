from django.db.models import Q
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from .models import Product
from .serializers import ProductSerializer


@api_view(["GET"])
def product_list(request):
    """
    GET /products/
    Optional query params: category, min_price, max_price, q
    """
    queryset = Product.objects.all()

    category = request.query_params.get("category")
    if category:
        queryset = queryset.filter(category__iexact=category)

    min_price = request.query_params.get("min_price")
    if min_price:
        queryset = queryset.filter(price_paise__gte=int(min_price))

    max_price = request.query_params.get("max_price")
    if max_price:
        queryset = queryset.filter(price_paise__lte=int(max_price))

    q = request.query_params.get("q")
    if q:
        queryset = queryset.filter(
            Q(name__icontains=q) | Q(description__icontains=q)
        )

    serializer = ProductSerializer(queryset, many=True)
    return Response(serializer.data)


@api_view(["GET"])
def product_detail(request, pk):
    """GET /products/<int:pk>/"""
    try:
        product = Product.objects.get(pk=pk)
    except Product.DoesNotExist:
        return Response(
            {"detail": "Product not found."}, status=status.HTTP_404_NOT_FOUND
        )

    serializer = ProductSerializer(product)
    return Response(serializer.data)
