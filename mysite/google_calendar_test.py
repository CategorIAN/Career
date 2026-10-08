from datetime import datetime, timedelta
import os
from zoneinfo import ZoneInfo

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mysite.settings")
django.setup()

from app.services.google_calendar import get_calendar_service

def main1():
    service = get_calendar_service()

    now = datetime.now(tz=ZoneInfo("UTC")).isoformat()

    result = service.events().list(
        calendarId="primary",
        timeMin=now,
        maxResults=10,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = result.get("items", [])

    for event in events:
        start = event["start"].get(
            "dateTime",
            event["start"].get("date"),
        )

        print(start, event.get("summary"))


def main2():
    service = get_calendar_service()

    start = datetime.now(ZoneInfo("America/Denver")) + timedelta(hours=1)
    end = start + timedelta(hours=1)

    event = {
        "summary": "Career App Test Event",
        "description": "Created from my Django Career app test script.",
        "start": {
            "dateTime": start.isoformat(),
            "timeZone": "America/Denver",
        },
        "end": {
            "dateTime": end.isoformat(),
            "timeZone": "America/Denver",
        },
    }

    created_event = (
        service.events()
        .insert(
            calendarId="primary",
            body=event,
        )
        .execute()
    )

    print("Created event:")
    print(created_event["summary"])
    print(created_event["id"])
    print(created_event.get("htmlLink"))


if __name__ == "__main__":
    main2()
