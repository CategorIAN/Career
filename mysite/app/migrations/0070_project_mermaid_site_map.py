from django.db import migrations, models


CAREER_SITE_MAP = """flowchart TD
    Visitor[Visitor] --> Home[Home]
    Home --> Resume[Resume]
    Home --> Experience[Experience]
    Home --> Projects[Projects]
    Home --> Education[Education]
    Home --> Contact[Contact]
    Resume --> Experience
    Resume --> Projects
    Resume --> Education
    Projects --> ProjectDiagram[E/R Diagram]
    Projects --> ProjectSiteMap[Site Map]
    Administrator[Career administrator] --> Management[Management]
    Administrator --> Networking[Networking]
    Administrator --> FindingWork[Finding Work]
    Management --> Companies[Companies]
    Management --> Skills[Skills]
    Networking --> Professionals[Professionals]
    Networking --> Connections[Connections]
    FindingWork --> JobSearch[Job Search]
    FindingWork --> Applications[Job Applications]
"""


EVENT_PLANNER_SITE_MAP = """flowchart TD
    Visitor[Visitor] --> Home[Event Planner Home]
    Home --> Login[Log in]
    Login --> Staff{Staff user?}
    Staff -->|Yes| Events[Events]
    Staff -->|Yes| Availability[Availability]
    Staff -->|Yes| FormSubmissions[Form Submissions]
    Staff -->|Yes| SurveyUpdates[Survey Updates]
    Staff -->|Yes| ERDiagram[E/R Diagram]
    Events --> CreateEvent[Create Event]
    Events --> EditEvent[Edit Event]
    Events --> Invitations[Send and update invitations]
    FormSubmissions --> SyncResponses[Sync Google Form responses]
    FormSubmissions --> CreatePerson[Create Person]
    FormSubmissions --> UpdatePerson[Update Person]
    SurveyUpdates --> RequestSurvey[Request survey update]
"""


def populate_project_site_maps(apps, schema_editor):
    Project = apps.get_model("app", "Project")
    Project.objects.filter(
        github_url="https://github.com/CategorIAN/Career",
        mermaid_site_map="",
    ).update(mermaid_site_map=CAREER_SITE_MAP)
    Project.objects.filter(
        title="Tabletop Event Planning Application",
        github_url="https://github.com/CategorIAN/Event_Planning",
        mermaid_site_map="",
    ).update(mermaid_site_map=EVENT_PLANNER_SITE_MAP)


class Migration(migrations.Migration):
    dependencies = [("app", "0069_applicationemail_html_body")]

    operations = [
        migrations.AddField(
            model_name="project",
            name="mermaid_site_map",
            field=models.TextField(blank=True),
        ),
        migrations.RunPython(populate_project_site_maps, migrations.RunPython.noop),
    ]
