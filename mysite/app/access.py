from django.conf import settings


def is_career_administrator(user):
    return bool(
        user
        and user.is_authenticated
        and user.get_username() == settings.CAREER_ADMIN_USERNAME
    )


def career_access(request):
    return {"career_is_admin": is_career_administrator(request.user)}
