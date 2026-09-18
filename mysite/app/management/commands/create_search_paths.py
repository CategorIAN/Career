from django.core.management.base import BaseCommand

from app.models import Company, Platform, SearchPath, SearchTerm


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
            create_path(company=company, platform=None, search_term=None)
            if company.supports_job_search_terms:
                for search_term in active_search_terms:
                    create_path(
                        company=company,
                        platform=None,
                        search_term=search_term,
                    )

        for platform in Platform.objects.filter(job_search_enabled=True):
            for search_term in active_search_terms:
                create_path(
                    company=None,
                    platform=platform,
                    search_term=search_term,
                )

        self.stdout.write(f"SearchPaths created: {created_count}")
        self.stdout.write(f"SearchPaths already existed: {existing_count}")
