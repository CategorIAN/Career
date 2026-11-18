"""Application-email persistence helpers."""

from app.models import ApplicationEmail
from app.services.gmail import get_email


def refresh_application_email_html(application_email: ApplicationEmail) -> bool:
    """Fetch and persist the Gmail HTML body for one saved application email.

    Args:
        application_email: The existing email record to refresh.

    Returns:
        True when Gmail provides an HTML body; otherwise, False.

    Raises:
        GmailError: If Gmail cannot retrieve the source message.

    Side Effects:
        Updates only ``ApplicationEmail.html_body`` when HTML is available.
    """
    gmail_email = get_email(application_email.gmail_message_id)
    html_body = gmail_email.get("html_body", "")
    if not html_body:
        return False

    application_email.html_body = html_body
    application_email.save(update_fields=["html_body"])
    return True
