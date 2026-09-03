"""
Seed three default PolicyRule rows (idempotent via update_or_create).

Usage:
    python manage.py seed_policy_rules
"""

from django.core.management.base import BaseCommand

from policy.models import PolicyRule


class Command(BaseCommand):
    help = "Seed default policy rules (idempotent)"

    def handle(self, *args, **options):
        rules = [
            {
                "rule_type": "spending_limit",
                "scope": "global",
                "defaults": {
                    "threshold_paise": 1_500_000,
                    "config": {},
                    "active": True,
                },
            },
            {
                "rule_type": "max_single_order",
                "scope": "global",
                "defaults": {
                    "threshold_paise": 800_000,
                    "config": {},
                    "active": True,
                },
            },
            {
                "rule_type": "category_approval",
                "scope": "global",
                "defaults": {
                    "threshold_paise": 500_000,
                    "config": {"category": "monitors"},
                    "active": True,
                },
            },
        ]

        for rule_kwargs in rules:
            obj, created = PolicyRule.objects.update_or_create(
                rule_type=rule_kwargs["rule_type"],
                scope=rule_kwargs["scope"],
                defaults=rule_kwargs["defaults"],
            )
            verb = "Created" if created else "Updated"
            # pyrefly: ignore [missing-attribute]
            self.stdout.write(self.style.SUCCESS(f"{verb}: {obj}"))
