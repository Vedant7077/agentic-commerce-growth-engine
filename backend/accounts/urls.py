from django.urls import path
from . import views

urlpatterns = [
    path("limit/", views.manage_spending_limit, name="manage-spending-limit"),
]
