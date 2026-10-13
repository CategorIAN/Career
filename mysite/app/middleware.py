from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse
from urllib.parse import urlencode

from .access import is_career_administrator


PUBLIC_PORTFOLIO_VIEW_NAMES = frozenset(
    {
        "home",
        "resume",
        "experience",
        "residencies",
        "projects",
        "courses",
    }
)
PUBLIC_AUTH_VIEW_NAMES = frozenset({"admin:login"})


class CareerAccessMiddleware:
    """Restrict Career management routes to the configured administrator."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        resolver_match = request.resolver_match
        if resolver_match.namespace == "admin":
            if resolver_match.view_name in PUBLIC_AUTH_VIEW_NAMES:
                return None
            if not request.user.is_authenticated:
                login_url = reverse("admin:login")
                return redirect(
                    f"{login_url}?{urlencode({'next': request.get_full_path()})}"
                )
            if is_career_administrator(request.user):
                return None
            raise PermissionDenied("The Django admin is only available to the Career administrator.")
        if (
            resolver_match.url_name in PUBLIC_PORTFOLIO_VIEW_NAMES
            or resolver_match.view_name in PUBLIC_AUTH_VIEW_NAMES
        ):
            return None
        if is_career_administrator(request.user):
            return None
        raise PermissionDenied("This page is only available to the Career administrator.")
