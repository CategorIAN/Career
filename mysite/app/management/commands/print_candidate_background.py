from django.core.management.base import BaseCommand

from app.services.candidate_background import build_candidate_background


class Command(BaseCommand):
    help = "Print the candidate background generated from Career app records."

    def handle(self, *args, **options):
        self.stdout.write(build_candidate_background())
