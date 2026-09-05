"""
Management command to seed ~30-40 realistic historical orders with clear growth-analytics patterns.

Patterns deliberately seeded for hackathon demo & growth engine analytics:
1. Product Affinity / Co-occurrence:
   - 'CodeBoard 75% Hot-Swap Keyboard' and 'PrecisionGlide Ergonomic Mouse'
     strongly co-occur across 12-15 orders (frequent bundle/basket affinity).
2. Underperforming Category / Cold Product:
   - 'EcoBright 21" HD Monitor' appears only once (underperforming product anomaly).
3. Realistic User Distribution:
   - Orders distributed across 6 demo customer profiles (tech developers, designers, gamers).
4. Realistic Historical Timestamps & Statuses:
   - Distributed over the past 45 days.
   - Status mix: majority 'paid'/'confirmed', a few 'pending', 'failed', 'blocked'.
"""

import random
import uuid
from datetime import timedelta
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from catalogue.models import Product
from orders.models import Order, OrderItem

DEMO_USER_PROFILES = [
    {"name": "Priya Sharma", "email": "priya.sharma@demo.com", "spending_limit_paise": 15000000},
    {"name": "Rahul Verma", "email": "rahul.verma@demo.com", "spending_limit_paise": 10000000},
    {"name": "Ananya Iyer", "email": "ananya.iyer@demo.com", "spending_limit_paise": 20000000},
    {"name": "Vikram Malhotra", "email": "vikram.m@demo.com", "spending_limit_paise": 12000000},
    {"name": "Sneha Patel", "email": "sneha.patel@demo.com", "spending_limit_paise": 18000000},
    {"name": "Rohan Das", "email": "rohan.das@demo.com", "spending_limit_paise": 8000000},
]


class Command(BaseCommand):
    help = "Seeds 30-40 realistic demo orders with intentional product co-occurrence and performance patterns."

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=36,
            help="Total number of demo orders to generate (default: 36).",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete existing demo-seeded orders and demo users before seeding.",
        )

    def handle(self, *args, **options):
        style: Any = self.style
        total_target = options["count"]
        clear_existing = options["clear"]

        if clear_existing:
            deleted_orders, _ = Order.objects.filter(idempotency_key__startswith="demo_").delete()
            deleted_users, _ = User.objects.filter(email__endswith="@demo.com").delete()
            self.stdout.write(
                style.WARNING(
                    f"Cleared {deleted_orders} previous demo orders and {deleted_users} demo users."
                )
            )

        # 1. Resolve or create Key Target Products for patterns
        codeboard = self._get_or_create_product(
            search_query="CodeBoard",
            fallback_name="CodeBoard 75% Hot-Swap Keyboard",
            category="keyboards",
            price_paise=799900,
            rating=4.7,
            description="Compact 75% layout with hot-swappable switches, designed for developers.",
        )

        mouse = self._get_or_create_product(
            search_query="PrecisionGlide",
            fallback_name="PrecisionGlide Ergonomic Mouse",
            category="mice",
            price_paise=349900,
            rating=4.6,
            description="Ergonomic vertical mouse with low-latency sensor for long coding sessions.",
        )

        monitor = self._get_or_create_product(
            search_query="EcoBright",
            fallback_name="EcoBright 21\" HD Monitor",
            category="monitors",
            price_paise=649900,
            rating=3.2,
            description="Budget 21-inch 1080p monitor with basic energy-saving panel.",
        )

        # Other available catalogue products for background variety
        other_products = list(
            Product.objects.exclude(id__in=[codeboard.id, mouse.id, monitor.id])
        )
        if not other_products:
            other_products = [codeboard, mouse]

        # 2. Ensure Demo Users exist
        users = []
        for profile in DEMO_USER_PROFILES:
            user, _ = User.objects.get_or_create(
                email=profile["email"],
                defaults={
                    "name": profile["name"],
                    "spending_limit_paise": profile["spending_limit_paise"],
                },
            )
            users.append(user)

        # Also include user #1 if present
        primary_user = User.objects.filter(id=1).first()
        if primary_user and primary_user not in users:
            users.append(primary_user)

        # 3. Generate Historical Orders
        now = timezone.now()
        created_orders = []
        co_occurrence_count = 0
        monitor_count = 0

        # Pattern distribution:
        # - ~14 orders contain BOTH CodeBoard + PrecisionGlide (strong co-occurrence bundle)
        # - ~5 orders contain CodeBoard alone or with other accessories
        # - ~4 orders contain PrecisionGlide alone or with other accessories
        # - Exactly 1 order contains EcoBright 21" HD Monitor (underperforming item)
        # - Remaining orders (~12) contain diverse accessories (headphones, other monitors, mice)

        self.stdout.write(f"Generating {total_target} synthetic historical orders...")

        with transaction.atomic():  # type: ignore
            for i in range(total_target):
                # Pick customer
                user = random.choice(users)

                # Determine item composition based on deliberate pattern goals
                items_to_add = []

                if i < 14:
                    # Co-occurrence bundle: CodeBoard + PrecisionGlide Mouse
                    items_to_add.append((codeboard, 1))
                    items_to_add.append((mouse, 1))
                    co_occurrence_count += 1
                    # Occasionally add a 3rd accessory
                    if random.random() < 0.35 and other_products:
                        items_to_add.append((random.choice(other_products), 1))

                elif i == 14:
                    # Single underperforming monitor order
                    items_to_add.append((monitor, 1))
                    monitor_count += 1

                elif i < 19:
                    # CodeBoard with another item
                    items_to_add.append((codeboard, 1))
                    if other_products and random.random() < 0.5:
                        items_to_add.append((random.choice(other_products), 1))

                elif i < 23:
                    # PrecisionGlide with another item
                    items_to_add.append((mouse, 1))
                    if other_products and random.random() < 0.5:
                        items_to_add.append((random.choice(other_products), 1))

                else:
                    # General diverse catalogue mix
                    k = random.choices([1, 2, 3], weights=[0.5, 0.4, 0.1])[0]
                    chosen = random.sample(other_products, min(k, len(other_products)))
                    for prod in chosen:
                        qty = random.choices([1, 2], weights=[0.85, 0.15])[0]
                        items_to_add.append((prod, qty))

                # Order Status Distribution
                # 75% paid, 15% confirmed, 5% pending, 5% failed
                status_roll = random.random()
                if status_roll < 0.75:
                    status = "paid"
                elif status_roll < 0.90:
                    status = "confirmed"
                elif status_roll < 0.95:
                    status = "pending"
                else:
                    status = "failed"

                # Razorpay order id for confirmed/paid
                rzp_id = (
                    f"order_demo_{uuid.uuid4().hex[:14]}"
                    if status in ("paid", "confirmed")
                    else None
                )

                # Idempotency key
                idem_key = f"demo_{uuid.uuid4().hex[:16]}"

                # Create Order
                order = Order.objects.create(
                    user=user,
                    status=status,
                    razorpay_order_id=rzp_id,
                    idempotency_key=idem_key,
                    total_paise=0,
                )

                # Create OrderItems & calculate total
                order_total = 0
                order_item_objs = []
                for prod, qty in items_to_add:
                    price_snap = prod.price_paise
                    order_total += price_snap * qty
                    order_item_objs.append(
                        OrderItem(
                            order=order,
                            product=prod,
                            quantity=qty,
                            price_paise_at_purchase=price_snap,
                        )
                    )

                OrderItem.objects.bulk_create(order_item_objs)

                # Set historical timestamp spread across the last 45 days
                # Earlier indices spread further back, latest indices are more recent
                days_ago = max(1, int(45 * (1 - (i / total_target)) + random.uniform(-2, 2)))
                hours_offset = random.randint(1, 23)
                minutes_offset = random.randint(0, 59)
                fake_time = now - timedelta(days=days_ago, hours=hours_offset, minutes=minutes_offset)

                # Update total and historical timestamp
                Order.objects.filter(pk=order.pk).update(
                    total_paise=order_total,
                    created_at=fake_time,
                )

                created_orders.append(order)

        # 4. Output Summary
        self.stdout.write(style.SUCCESS(f"\nSuccessfully seeded {len(created_orders)} demo orders!\n"))
        self.stdout.write("Pattern Verification:")
        self.stdout.write(
            f"  - Co-occurrence: 'CodeBoard 75%' + 'PrecisionGlide Mouse' bought together: {co_occurrence_count} times ({co_occurrence_count / total_target * 100:.1f}%)"
        )
        self.stdout.write(
            f"  - Underperforming: 'EcoBright 21\" HD Monitor' order count: {monitor_count} time(s)"
        )
        self.stdout.write(f"  - Customers active: {len(users)} users ({', '.join(u.name for u in users[:4])}...)")

        status_counts = {}
        for o in created_orders:
            # reload status
            status_counts[o.status] = status_counts.get(o.status, 0) + 1
        self.stdout.write(f"  - Order Statuses: {status_counts}")
        self.stdout.write("  - Date span: Past 45 days to today\n")

    def _get_or_create_product(self, search_query, fallback_name, category, price_paise, rating, description):
        style: Any = self.style
        prod = Product.objects.filter(name__icontains=search_query).first()
        if prod:
            return prod
        prod = Product.objects.create(
            name=fallback_name,
            category=category,
            price_paise=price_paise,
            rating=rating,
            stock=50,
            description=description,
        )
        self.stdout.write(style.NOTICE(f"Created missing product: {fallback_name} (₹{price_paise / 100:.2f})"))
        return prod
