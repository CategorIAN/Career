from datetime import timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.services.google_auth import get_google_credentials

CALENDAR_ID = "primary"
CALENDAR_TIME_ZONE = "America/Denver"
CALENDAR_TIMEZONE = ZoneInfo(CALENDAR_TIME_ZONE)


def get_calendar_service():
    return build("calendar", "v3", credentials=get_google_credentials())


def _event_result(status, message):
    return {"status": status, "message": message}


def _save_event_id(connect, field_name, event_id):
    setattr(connect, field_name, event_id)
    connect.save(update_fields=[field_name])


def _upsert_event(connect, *, event_id_field, event_body, event_kind, service):
    event_id = getattr(connect, event_id_field)
    events = service.events()

    if not event_id:
        created_event = events.insert(calendarId=CALENDAR_ID, body=event_body).execute()
        _save_event_id(connect, event_id_field, created_event["id"])
        return _event_result("created", f"{event_kind} created.")

    try:
        events.update(
            calendarId=CALENDAR_ID,
            eventId=event_id,
            body=event_body,
        ).execute()
        return _event_result("updated", f"{event_kind} updated.")
    except HttpError as error:
        if getattr(error.resp, "status", None) != 404:
            raise

    recreated_event = events.insert(calendarId=CALENDAR_ID, body=event_body).execute()
    _save_event_id(connect, event_id_field, recreated_event["id"])
    return _event_result("created", f"{event_kind} recreated after it was missing.")


def delete_meeting_event(connect, service=None):
    event_id = connect.google_meeting_event_id
    if not event_id:
        return _event_result("skipped", "No Google meeting event to delete.")

    try:
        (service or get_calendar_service()).events().delete(
            calendarId=CALENDAR_ID,
            eventId=event_id,
        ).execute()
    except HttpError as error:
        if getattr(error.resp, "status", None) != 404:
            raise

    connect.google_meeting_event_id = ""
    connect.save(update_fields=["google_meeting_event_id"])
    return _event_result("deleted", "Meeting deleted from Google Calendar.")


def sync_meeting_event(connect, service=None):
    if connect.meeting_at is None:
        return delete_meeting_event(connect, service=service)

    def as_calendar_datetime(value):
        if timezone.is_naive(value):
            return timezone.make_aware(value, CALENDAR_TIMEZONE)
        return timezone.localtime(value, CALENDAR_TIMEZONE)

    meeting_at = as_calendar_datetime(connect.meeting_at)
    meeting_end = as_calendar_datetime(
        connect.meeting_end or (connect.meeting_at + timedelta(hours=1))
    )
    event_body = {
        "summary": connect.description,
        "start": {
            "dateTime": meeting_at.isoformat(),
            "timeZone": CALENDAR_TIME_ZONE,
        },
        "end": {
            "dateTime": meeting_end.isoformat(),
            "timeZone": CALENDAR_TIME_ZONE,
        },
    }
    return _upsert_event(
        connect,
        event_id_field="google_meeting_event_id",
        event_body=event_body,
        event_kind="Meeting",
        service=service or get_calendar_service(),
    )


def sync_professional_connect(connect):
    if connect.meeting_at is None and not connect.google_meeting_event_id:
        return {"meeting": _event_result("skipped", "No meeting date to sync.")}

    try:
        service = get_calendar_service()
    except Exception as error:
        message = str(error)
        return {"meeting": _event_result("error", message)}

    try:
        return {"meeting": sync_meeting_event(connect, service=service)}
    except Exception as error:
        return {"meeting": _event_result("error", str(error))}
