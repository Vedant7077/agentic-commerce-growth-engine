from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import User
from policy.models import PolicyRule


@api_view(["GET", "POST"])
def manage_spending_limit(request):
    """
    GET /accounts/limit/   -> Returns User #1's spending limit
    POST /accounts/limit/  -> Updates User #1's spending limit and syncs policy rule
    Body: { "spending_limit_inr": 15000 } or { "spending_limit_paise": 1500000 }
    """
    user_id = request.query_params.get("user_id", 1)
    user, _ = User.objects.get_or_create(
        id=int(user_id),
        defaults={
            "name": "Test User",
            "email": "testuser@example.com",
            "spending_limit_paise": 1500000,
        },
    )

    if request.method == "POST":
        limit_inr = request.data.get("spending_limit_inr")
        limit_paise = request.data.get("spending_limit_paise")

        if limit_inr is not None:
            try:
                limit_paise = int(float(limit_inr) * 100)
            except (ValueError, TypeError):
                return Response(
                    {"detail": "Invalid spending_limit_inr format"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        elif limit_paise is not None:
            try:
                limit_paise = int(limit_paise)
            except (ValueError, TypeError):
                return Response(
                    {"detail": "Invalid spending_limit_paise format"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            return Response(
                {"detail": "spending_limit_inr or spending_limit_paise is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if limit_paise < 0:
            return Response(
                {"detail": "Spending limit cannot be negative"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.spending_limit_paise = limit_paise
        user.save()

        # Keep global policy rule in sync with the configured spending limit
        PolicyRule.objects.filter(rule_type="spending_limit").update(
            threshold_paise=limit_paise
        )

        return Response({
            "status": "success",
            "user_id": user.id,
            "spending_limit_paise": user.spending_limit_paise,
            "spending_limit_inr": user.spending_limit_paise / 100,
            "message": f"Spending limit updated to ₹{user.spending_limit_paise / 100:,.2f}",
        })

    return Response({
        "user_id": user.id,
        "name": user.name,
        "spending_limit_paise": user.spending_limit_paise,
        "spending_limit_inr": user.spending_limit_paise / 100,
    })
