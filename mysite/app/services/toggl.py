import base64
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from app.models import Project, TogglSyncStatus, TogglTimeEntry


class TogglSyncError(Exception):
    pass


@dataclass(frozen=True)
class TogglSyncResult:
    created: int = 0
    updated: int = 0
    ambiguous: int = 0
    running: int = 0
    reconciled_deleted: int = 0


def toggl_is_configured():
    return bool(getattr(settings, "TOGGL_API_TOKEN", ""))


def _parse_timestamp(value):
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed is None:
        raise TogglSyncError(f"Toggl returned an invalid timestamp: {value!r}")
    return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)


def fetch_time_entries(start, end):
    """Read Toggl v9 entries for the configured bounded import window."""
    token = getattr(settings, "TOGGL_API_TOKEN", "")
    if not token:
        raise TogglSyncError("TOGGL_API_TOKEN is not configured.")
    params = urlencode(
        {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        }
    )
    credentials = base64.b64encode(f"{token}:api_token".encode()).decode()
    request = Request(
        f"https://api.track.toggl.com/api/v9/me/time_entries?{params}",
        headers={"Authorization": f"Basic {credentials}", "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            entries = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise TogglSyncError(f"Toggl rejected the import ({error.code}).") from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise TogglSyncError("Could not retrieve Toggl time entries.") from error
    if not isinstance(entries, list):
        raise TogglSyncError("Toggl returned an unexpected time-entry response.")
    if len(entries) >= 1000:
        raise TogglSyncError(
            "The selected import window reached Toggl's 1,000-entry v9 limit; "
            "reduce TOGGL_IMPORT_DAYS before syncing."
        )
    return entries


def _project_matches_tags(tags, projects):
    normalized_tags = {str(tag).casefold() for tag in tags}
    return [
        project
        for project in projects
        if project.toggl_tag_name.casefold() in normalized_tags
    ]


def import_time_entries(entries, *, start, end):
    """Upsert a full bounded Toggl window and reconcile removed/retagged entries."""
    projects = list(Project.objects.exclude(toggl_tag_name=""))
    imported_ids = set()
    created = updated = ambiguous = running = 0
    with transaction.atomic():
        for entry in entries:
            external_id = str(entry.get("id", "")).strip()
            if not external_id:
                raise TogglSyncError("Toggl returned a time entry without an ID.")
            imported_ids.add(external_id)
            tags = entry.get("tags") or []
            if not isinstance(tags, list):
                tags = []
            matches = _project_matches_tags(tags, projects)
            is_ambiguous = len(matches) > 1
            duration = int(entry.get("duration") or 0)
            is_running = duration < 0 or not entry.get("stop")
            defaults = {
                "project": matches[0] if len(matches) == 1 else None,
                "source_project_id": str(entry.get("project_id") or entry.get("pid") or ""),
                "source_project_name": entry.get("project_name") or "",
                "description": entry.get("description") or "",
                "tags": tags,
                "started_at": _parse_timestamp(entry.get("start")),
                "stopped_at": _parse_timestamp(entry.get("stop")),
                "duration_seconds": 0 if is_running else max(duration, 0),
                "is_running": is_running,
                "is_ambiguous": is_ambiguous,
                "is_deleted_at_source": False,
            }
            _, was_created = TogglTimeEntry.objects.update_or_create(
                external_id=external_id,
                defaults=defaults,
            )
            created += int(was_created)
            updated += int(not was_created)
            ambiguous += int(is_ambiguous)
            running += int(is_running)

        reconciled_deleted = TogglTimeEntry.objects.filter(
            started_at__date__gte=start.date(),
            started_at__date__lte=end.date(),
            is_deleted_at_source=False,
        ).exclude(external_id__in=imported_ids).update(is_deleted_at_source=True)
        status, _ = TogglSyncStatus.objects.get_or_create(pk=1)
        status.last_successful_sync_at = timezone.now()
        status.last_error = ""
        status.coverage_start_date = start.date()
        status.coverage_end_date = end.date()
        status.save()
    return TogglSyncResult(created, updated, ambiguous, running, reconciled_deleted)


def sync_toggl_time_entries():
    days = max(1, int(getattr(settings, "TOGGL_IMPORT_DAYS", 365)))
    end = timezone.now()
    start = end - timedelta(days=days)
    try:
        result = import_time_entries(fetch_time_entries(start, end), start=start, end=end)
    except TogglSyncError as error:
        status, _ = TogglSyncStatus.objects.get_or_create(pk=1)
        status.last_error = str(error)
        status.save(update_fields=["last_error"])
        raise
    return result
