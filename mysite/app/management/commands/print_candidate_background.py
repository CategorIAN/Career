from typing import Any
from django.core.management.base import BaseCommand

from app.services.candidate_background import build_candidate_background


class Command(BaseCommand):
    help = "Print the candidate background generated from Career app records."

    def handle(self, *args: Any, **options: Any) -> None:
        """Runs the management command."""
        self.stdout.write(build_candidate_background())
