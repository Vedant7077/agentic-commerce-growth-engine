"""
LangChain tools for the product catalogue agent.

Each tool calls the Django REST API over HTTP using httpx,
so the Django dev server must be running for the agent to work.
"""

import httpx
from langchain_core.tools import tool

BASE_URL = "http://localhost:8000"


@tool
def search_catalogue(
    query: str,
    category: str = None,
    min_price: int = None,
    max_price: int = None,
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
