from typing import Any
from django.conf import settings


def is_career_administrator(user: Any) -> Any:
    """Executes this callable."""
    return bool(
        user
        and user.is_authenticated
        and user.get_username() == settings.CAREER_ADMIN_USERNAME
    )


def career_access(request: Any) -> dict[str, Any]:
    """Executes this callable."""
    return {"career_is_admin": is_career_administrator(request.user)}
