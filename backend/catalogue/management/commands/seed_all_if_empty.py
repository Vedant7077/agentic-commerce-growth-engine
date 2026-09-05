"""
Idempotent bootstrap seeder for fresh deployments.

Checks if the catalogue is empty — if so, seeds products, policy rules,
demo orders, and creates a default test buyer.  If data already exists,
the command is a no-op so it's safe to run on every boot.

Usage:
    python manage.py seed_all_if_empty
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand

from accounts.models import User
from catalogue.models import Product


class Command(BaseCommand):
    help = (
        "Seed products, policy rules, demo orders, and a test buyer "
        "only when the database is empty. Safe to run on every boot."
    )

    def handle(self, *args, **options):
        if Product.objects.count() > 0:
            self.stdout.write(
                self.style.NOTICE(
                    "Products already exist — skipping all seeding."
                )
            )
            return

        self.stdout.write("Database is empty — seeding data …")

        self.stdout.write("  → Seeding products …")
        call_command("seed_products", stdout=self.stdout, stderr=self.stderr)

        self.stdout.write("  → Seeding policy rules …")
        call_command("seed_policy_rules", stdout=self.stdout, stderr=self.stderr)

        self.stdout.write("  → Seeding demo orders …")
        call_command("seed_demo_orders", stdout=self.stdout, stderr=self.stderr)

        self.stdout.write("  → Ensuring test buyer exists …")
        user, created = User.objects.get_or_create(
            email="buyer@test.com",
            defaults={
                "name": "Test Buyer",
                "spending_limit_paise": 1_500_000,
            },
        )
        verb = "Created" if created else "Already exists"
        self.stdout.write(f"    {verb}: {user}")

        self.stdout.write(
            self.style.SUCCESS("All seeding completed successfully!")
        )
