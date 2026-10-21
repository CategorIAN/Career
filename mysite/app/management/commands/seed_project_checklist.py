from django.core.management.base import BaseCommand

from app.models import ChecklistItem
from app.services.project_management import seed_default_checklist_items


class Command(BaseCommand):
    help = "Create any missing shared Project Management checklist standards."

    def handle(self, *args, **options):
        before_count = ChecklistItem.objects.count()
        seed_default_checklist_items()
        created_count = ChecklistItem.objects.count() - before_count
        self.stdout.write(
            self.style.SUCCESS(f"Created {created_count} checklist standard(s).")
        )
