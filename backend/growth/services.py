"""
Raw SQL analytics for growth insights.

Both functions use django.db.connection.cursor() with raw SQL
(no ORM) as required for the self-join and aggregation queries.
"""

from django.db import connection


def get_frequently_bought_together(limit=10):
    """Return the top N product pairs most frequently ordered together.

    Uses a self-join on orders_orderitem with the constraint
    product_id_1 < product_id_2 to avoid duplicate reversed pairs.
    """
    sql = """
        SELECT oi1.product_id  AS product_id_1,
               oi2.product_id  AS product_id_2,
               p1.name         AS product_name_1,
               p2.name         AS product_name_2,
               COUNT(*)        AS times_bought_together
        FROM   orders_orderitem oi1
        JOIN   orders_orderitem oi2
               ON oi1.order_id = oi2.order_id
               AND oi1.product_id < oi2.product_id
        JOIN   catalogue_product p1 ON p1.id = oi1.product_id
        JOIN   catalogue_product p2 ON p2.id = oi2.product_id
        GROUP  BY oi1.product_id, oi2.product_id, p1.name, p2.name
        ORDER  BY times_bought_together DESC
        LIMIT  %s
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [limit])
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_underperforming_categories(threshold=3):
    """Return categories with fewer than `threshold` total order-items.

    Joins orders_orderitem to catalogue_product to group by category
    and filters using HAVING.
    """
    sql = """
        SELECT cp.category,
               COUNT(*) AS total_order_items
        FROM   orders_orderitem oi
        JOIN   catalogue_product cp ON cp.id = oi.product_id
        GROUP  BY cp.category
        HAVING COUNT(*) < %s
        ORDER  BY total_order_items ASC
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [threshold])
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
