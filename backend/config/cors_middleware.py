from django.conf import settings
from django.http import HttpResponse


class SimpleCorsMiddleware:
    """Lightweight CORS middleware that respects settings.CORS_ALLOWED_ORIGINS."""

    def __init__(self, get_response):
        self.get_response = get_response

    def _get_origin(self, request):
        """Return the allowed origin to echo back, or None."""
        origin = request.META.get("HTTP_ORIGIN", "")
        allowed = getattr(settings, "CORS_ALLOWED_ORIGINS", [])
        if origin in allowed:
            return origin
        # Allow all if the wildcard is configured
        if "*" in allowed:
            return origin or "*"
        return None

    def __call__(self, request):
        origin = self._get_origin(request)

        if request.method == "OPTIONS":
            response = HttpResponse()
        else:
            response = self.get_response(request)

        if origin:
            response["Access-Control-Allow-Origin"] = origin
            response["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            response["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"

        return response

