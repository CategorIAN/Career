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


def default_import_days():
    return max(1, int(getattr(settings, "TOGGL_IMPORT_DAYS", 365)))


def validate_import_days(days):
    if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
        raise TogglSyncError("Days back must be a positive whole number.")

    max_days = max(1, int(getattr(settings, "TOGGL_MAX_IMPORT_DAYS", 365)))
    if days > max_days:
        raise TogglSyncError(
            f"Toggl supports importing at most {max_days} days at a time."
        )
    return days


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
        detail = error.read().decode("utf-8", errors="replace")
        raise TogglSyncError(
            f"Toggl rejected the import ({error.code}): {detail}"
        ) from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise TogglSyncError("Could not retrieve Toggl time entries.") from error
    if not isinstance(entries, list):
        raise TogglSyncError("Toggl returned an unexpected time-entry response.")
    if len(entries) >= 1000:
        raise TogglSyncError(
            "The selected import window reached Toggl's 1,000-entry v9 limit; "
            "reduce Days back before syncing."
        )
    return entries


def fetch_toggl_projects():
    """Return the current user's Toggl project names keyed by project ID."""
    token = getattr(settings, "TOGGL_API_TOKEN", "")
    if not token:
        raise TogglSyncError("TOGGL_API_TOKEN is not configured.")
    credentials = base64.b64encode(f"{token}:api_token".encode()).decode()
    request = Request(
        "https://api.track.toggl.com/api/v9/me/projects",
        headers={"Authorization": f"Basic {credentials}", "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            projects = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise TogglSyncError(
            f"Toggl rejected the project lookup ({error.code}): {detail}"
        ) from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise TogglSyncError("Could not retrieve Toggl projects.") from error
    if isinstance(projects, dict):
        projects = projects.get("data", [])
    if not isinstance(projects, list):
        raise TogglSyncError("Toggl returned an unexpected project response.")
    return {
        str(project["id"]): project["name"]
        for project in projects
        if project.get("id") is not None and project.get("name")
    }


def _project_matches_tags(tags, projects):
    normalized_tags = {str(tag).casefold() for tag in tags}
    return [
        project
        for project in projects
        if project.toggl_tag_name.casefold() in normalized_tags
    ]


def refresh_source_project_names(source_project_names):
    """Refresh stored Toggl activity names from a non-empty ID-to-name mapping."""
    if not source_project_names:
        return 0

    entries_to_update = []
    for entry in TogglTimeEntry.objects.filter(
        source_project_id__in=source_project_names,
    ).only("pk", "source_project_id", "source_project_name"):
        resolved_name = source_project_names.get(entry.source_project_id)
        if resolved_name and entry.source_project_name != resolved_name:
            entry.source_project_name = resolved_name
            entries_to_update.append(entry)

    if entries_to_update:
        TogglTimeEntry.objects.bulk_update(entries_to_update, ["source_project_name"])
    return len(entries_to_update)


def import_time_entries(entries, *, start, end, source_project_names=None):
    """Upsert a full bounded Toggl window and reconcile removed/retagged entries."""
    projects = list(Project.objects.exclude(toggl_tag_name=""))
    source_project_names = source_project_names or {}
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
            source_project_id = str(entry.get("project_id") or entry.get("pid") or "")
            source_project_name = (
                source_project_names.get(source_project_id)
                or entry.get("project_name")
                or ""
            )
            defaults = {
                "project": matches[0] if len(matches) == 1 else None,
                "source_project_id": source_project_id,
                "description": entry.get("description") or "",
                "tags": tags,
                "started_at": _parse_timestamp(entry.get("start")),
                "stopped_at": _parse_timestamp(entry.get("stop")),
                "duration_seconds": 0 if is_running else max(duration, 0),
                "is_running": is_running,
                "is_ambiguous": is_ambiguous,
                "is_deleted_at_source": False,
            }
            if source_project_name:
                defaults["source_project_name"] = source_project_name
            _, was_created = TogglTimeEntry.objects.update_or_create(
                external_id=external_id,
                defaults=defaults,
            )
            created += int(was_created)
            updated += int(not was_created)
            ambiguous += int(is_ambiguous)
            running += int(is_running)

        reconciled_deleted = TogglTimeEntry.objects.filter(
            started_at__gte=start,
            started_at__lte=end,
            is_deleted_at_source=False,
        ).exclude(external_id__in=imported_ids).update(is_deleted_at_source=True)
        status, _ = TogglSyncStatus.objects.get_or_create(pk=1)
        status.last_successful_sync_at = timezone.now()
        status.last_error = ""
        status.coverage_start_date = start.date()
        status.coverage_end_date = end.date()
        status.save()
    return TogglSyncResult(created, updated, ambiguous, running, reconciled_deleted)


def sync_toggl_time_entries(*, days_back=None):
    days = default_import_days() if days_back is None else validate_import_days(days_back)
    end = timezone.now()
    start = end - timedelta(days=days)
    try:
        source_project_names = fetch_toggl_projects()
        result = import_time_entries(
            fetch_time_entries(start, end),
            start=start,
            end=end,
            source_project_names=source_project_names,
        )
        refresh_source_project_names(source_project_names)
    except TogglSyncError as error:
        status, _ = TogglSyncStatus.objects.get_or_create(pk=1)
        status.last_error = str(error)
        status.save(update_fields=["last_error"])
        raise
    return result
