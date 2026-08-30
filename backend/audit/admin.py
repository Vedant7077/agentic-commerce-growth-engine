from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("id", "event_type", "actor", "order_id", "created_at")
    list_filter = ("event_type",)
    search_fields = ("actor", "event_type")
