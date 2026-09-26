from dataclasses import dataclass

from app.models import Company, SearchPath, SearchTerm


@dataclass(frozen=True)
class SearchPathCreationResult:
    created: int = 0
    existing: int = 0


def create_company_search_paths(
    company: Company,
    *,
    active_search_terms=None,
) -> SearchPathCreationResult:
    """Create every valid SearchPath for an enabled Company."""
    if not company.job_search_enabled:
        return SearchPathCreationResult()

    created_count = 0
    existing_count = 0

    def create_path(search_term):
        nonlocal created_count, existing_count
        _, created = SearchPath.objects.get_or_create(
            company=company,
            platform=None,
            search_term=search_term,
        )
        if created:
            created_count += 1
        else:
            existing_count += 1

    create_path(search_term=None)
    if company.supports_job_search_terms:
        active_search_terms = (
            SearchTerm.objects.filter(active=True)
            if active_search_terms is None
            else active_search_terms
        )
        for search_term in active_search_terms:
            create_path(search_term=search_term)

    return SearchPathCreationResult(created_count, existing_count)
