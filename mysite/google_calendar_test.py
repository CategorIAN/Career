import datetime
import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


SCOPES = ["https://www.googleapis.com/auth/calendar"]

def main1():
    creds = None

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file(
            "token.json",
            SCOPES,
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json",
                SCOPES,
            )

            creds = flow.run_local_server(port=0)

        with open("token.json", "w") as token:
            token.write(creds.to_json())

    service = build(
        "calendar",
        "v3",
        credentials=creds,
    )

    now = datetime.datetime.now(
        tz=datetime.timezone.utc
    ).isoformat()

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
    creds = None

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file(
            "token.json",
            SCOPES,
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json",
                SCOPES,
            )

            creds = flow.run_local_server(port=0)

        with open("token.json", "w") as token:
            token.write(creds.to_json())

    service = build(
        "calendar",
        "v3",
        credentials=creds,
    )

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