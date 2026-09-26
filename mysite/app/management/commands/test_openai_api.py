import os

from django.core.management.base import BaseCommand, CommandError
from openai import OpenAI


class Command(BaseCommand):
    help = "Send a basic prompt through the OpenAI Responses API."

    def handle(self, *args, **options):
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise CommandError(
                "Set the OPENAI_API_KEY environment variable before running this command."
            )

        client = OpenAI(api_key=api_key)
        response = client.responses.create(
            model="gpt-5.5",
            input="Explain what a Django QuerySet is in one paragraph.",
        )

        self.stdout.write(response.output_text)
