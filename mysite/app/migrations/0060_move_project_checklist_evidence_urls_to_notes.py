from django.db import migrations


def move_evidence_urls_to_notes(apps, schema_editor):
    ProjectChecklist = apps.get_model("app", "ProjectChecklist")
    for response in ProjectChecklist.objects.exclude(evidence_url=""):
        evidence_url = response.evidence_url.strip()
        if not evidence_url:
            continue
        evidence_note = f"Evidence URL: {evidence_url}"
        notes = response.notes.strip()
        if evidence_note not in notes:
            response.notes = f"{notes}\n\n{evidence_note}".strip()
            response.save(update_fields=["notes"])


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0059_checklistitem_togglsyncstatus_and_more"),
    ]

    operations = [
        migrations.RunPython(move_evidence_urls_to_notes, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="projectchecklist",
            name="evidence_url",
        ),
    ]
