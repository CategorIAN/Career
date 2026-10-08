"""Gmail API operations with no Django database persistence."""

import base64
import binascii
from datetime import UTC, datetime

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.services.google_auth import get_google_credentials


class GmailError(RuntimeError):
    """A Gmail API operation failed."""


def get_gmail_service():
    return build("gmail", "v1", credentials=get_google_credentials())


def search_emails(query="", max_results=50, page_token=None):
    """Return Gmail message/thread identifiers and an optional next-page token."""
    request = {
        "userId": "me",
        "q": query,
        "maxResults": max_results,
    }
    if page_token:
        request["pageToken"] = page_token
    try:
        result = get_gmail_service().users().messages().list(**request).execute()
    except HttpError as error:
        raise GmailError("Unable to search Gmail messages.") from error

    return {
        "messages": [
            {"message_id": message["id"], "thread_id": message["threadId"]}
            for message in result.get("messages", [])
        ],
        "next_page_token": result.get("nextPageToken"),
    }


def _decode_body(data):
    if not data:
        return ""
    padding = "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(data + padding).decode("utf-8", errors="replace")
    except (ValueError, binascii.Error):
        return ""


def _body_parts(part):
    if part.get("filename"):
        return [], []

    plain_parts = []
    html_parts = []
    mime_type = part.get("mimeType", "")
    body_data = part.get("body", {}).get("data")
    if mime_type == "text/plain" and body_data:
        plain_parts.append(_decode_body(body_data))
    elif mime_type == "text/html" and body_data:
        html_parts.append(_decode_body(body_data))

    for child_part in part.get("parts", []):
        child_plain, child_html = _body_parts(child_part)
        plain_parts.extend(child_plain)
        html_parts.extend(child_html)
    return plain_parts, html_parts


def _header_map(headers):
    return {header.get("name", "").lower(): header.get("value", "") for header in headers}


def get_email(message_id):
    """Fetch and parse one complete Gmail message without rendering its HTML."""
    try:
        message = (
            get_gmail_service()
            .users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
    except HttpError as error:
        raise GmailError(f"Unable to retrieve Gmail message {message_id}.") from error

    payload = message.get("payload", {})
    headers = _header_map(payload.get("headers", []))
    plain_parts, html_parts = _body_parts(payload)
    recipients = headers.get("to", "")
    if headers.get("cc"):
        recipients = ", ".join(part for part in [recipients, headers["cc"]] if part)
    received_at = None
    if message.get("internalDate"):
        try:
            received_at = datetime.fromtimestamp(
                int(message["internalDate"]) / 1000,
                tz=UTC,
            )
        except (TypeError, ValueError, OSError):
            received_at = None
    return {
        "message_id": message.get("id", message_id),
        "thread_id": message.get("threadId", ""),
        "subject": headers.get("subject", ""),
        "sender": headers.get("from", ""),
        "recipients": recipients,
        "date": headers.get("date", ""),
        "sent_received_date": headers.get("date", ""),
        "received_at": received_at,
        "plain_text_body": "\n".join(part for part in plain_parts if part),
        "html_body": "\n".join(part for part in html_parts if part),
        "label_ids": message.get("labelIds", []),
    }


def get_or_create_label(name):
    """Return the Gmail label ID for a user label, creating it when absent."""
    service = get_gmail_service()
    try:
        labels = service.users().labels().list(userId="me").execute().get("labels", [])
        for label in labels:
            if label.get("name") == name:
                return label["id"]
        label = (
            service.users()
            .labels()
            .create(
                userId="me",
                body={
                    "name": name,
                    "labelListVisibility": "labelShow",
                    "messageListVisibility": "show",
                },
            )
            .execute()
        )
        return label["id"]
    except HttpError as error:
        raise GmailError(f"Unable to get or create Gmail label {name!r}.") from error


def apply_labels(message_id, label_ids):
    """Apply only the supplied Gmail labels to a message."""
    try:
        return (
            get_gmail_service()
            .users()
            .messages()
            .modify(
                userId="me",
                id=message_id,
                body={"addLabelIds": list(label_ids)},
            )
            .execute()
        )
    except HttpError as error:
        raise GmailError(f"Unable to label Gmail message {message_id}.") from error


def apply_labels_and_archive(message_id, label_ids):
    """Apply supplied labels and remove only Gmail's INBOX label."""
    try:
        return (
            get_gmail_service()
            .users()
            .messages()
            .modify(
                userId="me",
                id=message_id,
                body={
                    "addLabelIds": list(label_ids),
                    "removeLabelIds": ["INBOX"],
                },
            )
            .execute()
        )
    except HttpError as error:
        raise GmailError(f"Unable to label and archive Gmail message {message_id}.") from error


def remove_labels(message_id, label_ids):
    """Remove only the supplied Gmail labels from a message."""
    try:
        return (
            get_gmail_service()
            .users()
            .messages()
            .modify(
                userId="me",
                id=message_id,
                body={"removeLabelIds": list(label_ids)},
            )
            .execute()
        )
    except HttpError as error:
        raise GmailError(f"Unable to remove Gmail labels from message {message_id}.") from error
