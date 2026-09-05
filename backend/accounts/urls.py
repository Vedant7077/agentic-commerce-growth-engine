from django.urls import path
from . import views

urlpatterns = [
    path("", views.manage_spending_limit, name="manage-spending-limit-root"),
    path("limit/", views.manage_spending_limit, name="manage-spending-limit"),
]
