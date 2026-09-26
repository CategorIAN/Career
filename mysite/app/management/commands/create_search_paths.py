from django.core.management.base import BaseCommand

from app.models import Company, Platform, SearchPath, SearchTerm
from app.services.search_paths import create_company_search_paths


class Command(BaseCommand):
    help = "Create missing valid SearchPath records for enabled companies and platforms."

    def handle(self, *args, **options):
        created_count = 0
        existing_count = 0
        active_search_terms = list(SearchTerm.objects.filter(active=True))

        def create_path(**lookup):
            nonlocal created_count, existing_count
            _, created = SearchPath.objects.get_or_create(**lookup)
            if created:
                created_count += 1
            else:
                existing_count += 1

        for company in Company.objects.filter(job_search_enabled=True):
            result = create_company_search_paths(
                company,
                active_search_terms=active_search_terms,
            )
            created_count += result.created
            existing_count += result.existing

        for platform in Platform.objects.filter(job_search_enabled=True):
            for search_term in active_search_terms:
                create_path(
                    company=None,
                    platform=platform,
                    search_term=search_term,
                )

        self.stdout.write(f"SearchPaths created: {created_count}")
        self.stdout.write(f"SearchPaths already existed: {existing_count}")
