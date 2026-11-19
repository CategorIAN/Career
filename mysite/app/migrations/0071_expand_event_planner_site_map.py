from django.db import migrations


EVENT_PLANNER_SITE_MAP = """flowchart TD
    Visitor[Visitor] --> PublicRoute{Public route?}
    PublicRoute -->|Home| Home[Event Planner Home]
    PublicRoute -->|Login| Login[Login]
    PublicRoute -->|No| Authenticated{Authenticated staff user?}
    Authenticated -->|No| Login
    Authenticated -->|Yes| StaffArea[Staff area]

    subgraph Navigation[Sidebar navigation]
        Home --> HomeLogin([Login]) --> Login
        Login --> StaffArea
        StaffArea --> Events[Events]
        StaffArea --> Availability[Availability]
        StaffArea --> ERDiagram[E/R Diagram]
        StaffArea --> FormSubmissions[Form Submissions]
        StaffArea --> SurveyUpdates[Survey Updates]
        StaffArea --> Admin[Django Admin]
        StaffArea --> Logout([Logout]) --> Login
    end

    subgraph EventWorkflow[Events page and event management]
        Events --> AddEvent([Add Event]) --> CreateEvent[Create Event]
        CreateEvent --> Events
        Events --> SelectEvent([Select Event]) --> EventDetails[Selected Event Details]
        EventDetails --> EditEvent([Edit]) --> SaveEvent[Save Event Changes] --> Events
        EventDetails --> EventPhoto([Add or Edit Photo]) --> SavePhoto[Save Photo] --> Events
        EventDetails --> DeletePhoto([Delete Photo]) --> Events
        EventDetails --> Happened([Happened?]) --> SetHappened[Set Event Outcome] --> Events
        EventDetails --> InviteList([Show Invitation List]) --> SendInvite[Send Invitation] --> Events
        EventDetails --> PreGame([Show Pre-Game Invitations]) --> InvitationBoard[Invitation Board]
        InvitationBoard --> UpdateResult[Update Invitation Result] --> Events
        InvitationBoard --> UpdatePlusOnes[Adjust Plus Ones] --> Events
        EventDetails --> PostGame([Show Post-Game Results]) --> Attendance[Attendance Actions]
        Attendance --> MarkAttending[Mark Attending] --> Events
        Attendance --> MarkAttended[Mark Attended] --> Events
        Attendance --> MarkFlaked[Mark Flaked] --> Events
    end

    subgraph AvailabilityWorkflow[Availability page]
        Availability --> ToggleGame([Show Game Availability]) --> AvailabilityGrid[Availability Grid]
        AvailabilityGrid --> CountCell([Select Count]) --> AvailabilityModal[Qualified People Details]
    end

    subgraph SubmissionWorkflow[Form submissions page]
        FormSubmissions --> SyncResponses([Sync Google Form Responses]) --> FormSubmissions
        FormSubmissions --> CreatePerson([Create Person]) --> FormSubmissions
        FormSubmissions --> OpenUpdateDrawer([Open Update Drawer]) --> UpdateDrawer[Matching People]
        UpdateDrawer --> UpdatePerson([Select or Update Person]) --> FormSubmissions
    end

    subgraph SurveyWorkflow[Survey updates page]
        SurveyUpdates --> DueOnly([Filter Due Only]) --> SurveyUpdates
        SurveyUpdates --> SelectSurveyForm[Select Survey Form]
        SelectSurveyForm --> RequestUpdate([Request Survey Update]) --> EmailConfirmation[Email Confirmation]
        EmailConfirmation --> SurveyUpdates
    end
"""


def expand_event_planner_site_map(apps, schema_editor):
    Project = apps.get_model("app", "Project")
    Project.objects.filter(
        title="Tabletop Event Planning Application",
        github_url="https://github.com/CategorIAN/Event_Planning",
    ).update(mermaid_site_map=EVENT_PLANNER_SITE_MAP)


class Migration(migrations.Migration):
    dependencies = [("app", "0070_project_mermaid_site_map")]

    operations = [
        migrations.RunPython(expand_event_planner_site_map, migrations.RunPython.noop),
    ]
