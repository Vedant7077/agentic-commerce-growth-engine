from django.contrib import admin

from .models import PolicyRule


@admin.register(PolicyRule)
class PolicyRuleAdmin(admin.ModelAdmin):
    # pyrefly: ignore [bad-override-mutable-attribute]
    list_display = ("id", "rule_type", "scope", "threshold_paise", "active")
    list_filter = ("rule_type", "active")
