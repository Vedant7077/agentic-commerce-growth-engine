from django.urls import path

from . import views

urlpatterns = [
    path("start/", views.agent_start, name="agent-start"),
    path("<str:thread_id>/confirm/", views.agent_confirm, name="agent-confirm"),
]
