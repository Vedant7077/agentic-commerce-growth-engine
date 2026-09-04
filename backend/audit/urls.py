from django.urls import path

from . import views

urlpatterns = [
    path("<str:identifier>/", views.audit_events_for_order, name="audit-events"),
]
