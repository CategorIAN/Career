from django.db import migrations


MERMAID_SOURCE = """erDiagram
    DAY {
        bigint id PK
        string name UK
        int order UK
    }
    HOUR {
        bigint id PK
        time time UK
    }
    DAY_HOUR {
        bigint id PK
        bigint day_id FK "unique with hour_id"
        bigint hour_id FK "unique with day_id"
    }
    TIME_SPAN {
        bigint id PK
        bigint day_id FK "unique with start_hour_id and end_hour_id"
        bigint start_hour_id FK "unique with day_id and end_hour_id"
        bigint end_hour_id FK "unique with day_id and start_hour_id"
    }
    DURATION {
        bigint id PK
        string name
        int days
    }
    GAME_TYPE {
        bigint id PK
        string name UK
        string url "blank allowed"
    }
    GAME {
        bigint id PK
        string name UK
        string url "blank allowed"
        string boardgamegeek_url "blank allowed"
        bigint game_type_id FK
        int expected_duration_hours "nullable"
        int min_players "nullable"
        int max_players "nullable"
    }
    PLATFORM {
        bigint id PK
        string name UK
        string url "blank allowed"
    }
    PERSON {
        bigint id PK
        string name
        string email "blank allowed"
        int max_game_hours "nullable"
        string status
        interval earliest_invite_lead "nullable"
        interval latest_invite_lead "nullable"
        string guest_games "blank allowed"
        interval event_cooldown "nullable"
        string role
    }
    FORM {
        bigint id PK
        string name
        string google_form_id UK
        string survey_url "blank allowed"
        datetime last_synced_at "nullable"
    }
    FORM_QUESTION_GROUP {
        bigint id PK
        bigint form_id FK
        string google_item_id
        string name
    }
    FORM_QUESTION {
        bigint id PK
        bigint form_id FK "unique with google_question_id"
        bigint group_id FK "nullable"
        string google_question_id "unique with form_id"
        string name
        bigint hour_id FK "nullable"
    }
    FORM_QUESTION_CHOICE {
        bigint id PK
        bigint question_id FK "unique with google_value"
        string google_value "unique with question_id"
        string value
        bigint game_id FK "nullable"
        bigint platform_id FK "nullable"
        bigint game_type_id FK "nullable"
        bigint duration_id FK "nullable"
    }
    FORM_REQUEST {
        bigint id PK
        bigint person_id FK
        bigint form_id FK
        datetime requested_at
    }
    FORM_SUBMISSION {
        bigint id PK
        bigint form_id FK "unique with google_response_id and submitted_at"
        bigint person_id FK "nullable"
        string google_response_id "unique with form_id and submitted_at"
        string submitted_name "blank allowed"
        string submitted_email "blank allowed"
        datetime submitted_at "unique with form_id and google_response_id"
        json raw_response_data
    }
    FORM_QUESTION_GROUP_CHOICE {
        bigint id PK
        bigint group_id FK "unique with google_value"
        string google_value "unique with group_id"
        bigint day_id FK "nullable"
    }
    EVENT {
        bigint id PK
        datetime timestamp
        bigint time_span_id FK
        bigint game_id FK
        boolean happened "nullable"
        bigint leader_id FK
    }
    INVITATION {
        bigint id PK
        bigint event_id FK "unique with person_id"
        bigint person_id FK "unique with event_id"
        datetime invited_at
        int plus_ones
        string result
    }

    DAY ||--o{ DAY_HOUR : day
    HOUR ||--o{ DAY_HOUR : hour
    DAY ||--o{ TIME_SPAN : day
    HOUR ||--o{ TIME_SPAN : start_hour
    HOUR ||--o{ TIME_SPAN : end_hour
    TIME_SPAN }o--o{ DAY_HOUR : day_hours
    GAME_TYPE ||--o{ GAME : game_type
    PERSON }o--o{ DAY_HOUR : availability
    PERSON }o--o{ GAME : games
    PERSON }o--o{ GAME_TYPE : game_types
    PERSON }o--o{ PLATFORM : platforms
    FORM ||--o{ FORM_QUESTION_GROUP : question_groups
    FORM ||--o{ FORM_QUESTION : questions
    FORM_QUESTION_GROUP o|--o{ FORM_QUESTION : group
    HOUR o|--o{ FORM_QUESTION : hour
    FORM_QUESTION ||--o{ FORM_QUESTION_CHOICE : choices
    GAME o|--o{ FORM_QUESTION_CHOICE : game
    PLATFORM o|--o{ FORM_QUESTION_CHOICE : platform
    GAME_TYPE o|--o{ FORM_QUESTION_CHOICE : game_type
    DURATION o|--o{ FORM_QUESTION_CHOICE : duration
    PERSON ||--o{ FORM_REQUEST : person
    FORM ||--o{ FORM_REQUEST : form
    FORM ||--o{ FORM_SUBMISSION : form
    PERSON o|--o{ FORM_SUBMISSION : person
    FORM_QUESTION_GROUP ||--o{ FORM_QUESTION_GROUP_CHOICE : group
    DAY o|--o{ FORM_QUESTION_GROUP_CHOICE : day
    TIME_SPAN ||--o{ EVENT : time_span
    GAME ||--o{ EVENT : game
    PERSON ||--o{ EVENT : leader
    EVENT ||--o{ INVITATION : event
    PERSON ||--o{ INVITATION : person
"""


def populate_event_planner_diagram(apps, schema_editor):
    Project = apps.get_model("app", "Project")
    Project.objects.filter(
        title="Tabletop Event Planning Application",
        github_url="https://github.com/CategorIAN/Event_Planning",
    ).update(mermaid_er_diagram=MERMAID_SOURCE)


class Migration(migrations.Migration):
    dependencies = [("app", "0066_project_mermaid_er_diagram")]

    operations = [
        migrations.RunPython(populate_event_planner_diagram, migrations.RunPython.noop),
    ]
