from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0061_simplify_project_checklist"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectchecklist",
            name="archived",
            field=models.BooleanField(default=False),
        ),
    ]
