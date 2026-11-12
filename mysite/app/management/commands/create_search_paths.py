from typing import Any
from django.core.management.base import BaseCommand

from app.models import Company, Platform, SearchTerm
from app.services.search_paths import (
    create_company_search_paths,
    create_platform_search_paths,
)


class Command(BaseCommand):
    help = "Create missing valid SearchPath records for enabled companies and platforms."

    def handle(self, *args: Any, **options: Any) -> None:
        """Runs the management command."""
        created_count = 0
        existing_count = 0
        active_search_terms = list(SearchTerm.objects.filter(active=True))

        for company in Company.objects.filter(job_search_enabled=True):
            result = create_company_search_paths(
                company,
                active_search_terms=active_search_terms,
            )
            created_count += result.created
            existing_count += result.existing

        for platform in Platform.objects.filter(job_search_enabled=True):
            result = create_platform_search_paths(
                platform,
                active_search_terms=active_search_terms,
            )
            created_count += result.created
            existing_count += result.existing

        self.stdout.write(f"SearchPaths created: {created_count}")
        self.stdout.write(f"SearchPaths already existed: {existing_count}")
