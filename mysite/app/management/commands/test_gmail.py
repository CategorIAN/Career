from django.core.management.base import BaseCommand, CommandError

from app.services.gmail import GmailError, get_email, search_emails
from app.services.google_auth import GoogleAuthError


class Command(BaseCommand):
    help = "Authenticate with Gmail and display a small sample of recent message metadata."

    def handle(self, *args, **options):
        try:
            result = search_emails(max_results=5)
        except (GmailError, GoogleAuthError) as error:
            raise CommandError(f"Gmail test failed: {error}") from error

        messages = result["messages"]
        if not messages:
            self.stdout.write("No Gmail messages found.")
            return

        self.stdout.write("Recent Gmail messages:")
        parsed_count = 0
        for message in messages:
            try:
                parsed = get_email(message["message_id"])
            except GmailError as error:
                self.stderr.write(
                    f"- {message['message_id']}: unable to parse message ({error})"
                )
                continue
            parsed_count += 1
            self.stdout.write(
                f"- {parsed['date']} | {parsed['sender']} | {parsed['subject']} "
                f"| {parsed['message_id']}"
            )

        if not parsed_count:
            raise CommandError("Unable to parse any of the retrieved Gmail messages.")
        self.stdout.write(
            f"Parsed {parsed_count} message(s) successfully without printing message bodies."
        )
