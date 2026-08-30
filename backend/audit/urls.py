from django.urls import path

from . import views

urlpatterns = [
    path("<int:order_id>/", views.audit_events_for_order, name="audit-events"),
]
