from django.db import migrations, models
from django.utils import timezone


def preserve_verification_dates(apps, schema_editor):
    ProjectChecklist = apps.get_model("app", "ProjectChecklist")
    for response in ProjectChecklist.objects.exclude(last_verified_at__isnull=True):
        verified_at = response.last_verified_at
        if timezone.is_aware(verified_at):
            verified_at = timezone.localtime(verified_at)
        response.updated_at = verified_at.date()
        response.save(update_fields=["updated_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0060_move_project_checklist_evidence_urls_to_notes"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectchecklist",
            name="updated_at",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.RunPython(preserve_verification_dates, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="projectchecklist",
            name="status",
        ),
        migrations.RemoveField(
            model_name="projectchecklist",
            name="last_verified_at",
        ),
    ]
