from django.utils import timezone

from app.models import ChecklistItem, ProjectChecklist


DEFAULT_CHECKLIST_ITEMS = (
    ("README and setup instructions", "Explain how to run or reproduce the project.", 180),
    ("Code clarity and useful comments", "Keep the code understandable and comments useful.", 180),
    ("Written report/paper", "Provide a report or paper when it supports the project.", 365),
    ("Architecture and data-flow diagram", "Document the architecture and major data flows.", 365),
    ("ER diagram", "Document the data model when an ER diagram applies.", 365),
    ("Meaningful tests or reproducible verification", "Record tests or repeatable verification steps.", 180),
    ("Accurate portfolio description and working links", "Keep public descriptions and links current.", 90),
)


def seed_default_checklist_items():
    """Create the shared project-review standards without duplicating them."""
    for name, guidance, interval in DEFAULT_CHECKLIST_ITEMS:
        ChecklistItem.objects.get_or_create(
            name=name,
            defaults={
                "guidance": guidance,
                "review_interval_days": interval,
            },
        )


def review_is_due(response, now=None):
    if response.update_due is None:
        return False
    today = now or timezone.localdate()
    return response.update_due <= today
