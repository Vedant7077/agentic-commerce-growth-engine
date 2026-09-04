from django.urls import path

from growth.views import analyze_growth

urlpatterns = [
    path("analyze/", analyze_growth, name="growth-analyze"),
]
