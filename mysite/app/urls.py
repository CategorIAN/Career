from django.urls import path
from . import views

urlpatterns = [
    path("", views.home_view, name="home"),
    path("skills/", views.skill_formset_view, name="skills"),
    path("platforms/", views.platform_formset_view, name="platforms"),
    path("professionals/", views.professional_formset_view, name="professionals"),
    path("recruiters/", views.recruiter_formset_view, name="recruiters"),
    path("companies/", views.companies_view, name="companies"),
    path("search-terms/", views.search_terms_view, name="search_terms"),
    path("job-search/", views.job_search_view, name="job_search"),
    path("job-postings/", views.job_postings_view, name="job_postings"),
    path("emails/", views.emails_view, name="emails"),
    path(
        "emails/<str:message_id>/applications/",
        views.email_application_options_view,
        name="email_application_options",
    ),
    path("job-applications/", views.job_applications_view, name="job_applications"),
    path(
        "application-details/",
        views.application_details_view,
        name="application_details",
    ),
    path(
        "interview-practice/<int:session_id>/",
        views.interview_practice_session_view,
        name="interview_practice_session",
    ),
    path(
        "interview-practice/<int:session_id>/opening/",
        views.interview_practice_opening_view,
        name="interview_practice_opening",
    ),
    path(
        "interview-practice/<int:session_id>/messages/",
        views.interview_practice_message_view,
        name="interview_practice_message",
    ),
    path(
        "interview-practice/<int:session_id>/end/",
        views.end_interview_practice_session_view,
        name="end_interview_practice_session",
    ),
    path(
        "interview-practice/<int:session_id>/feedback/",
        views.retry_interview_practice_feedback_view,
        name="retry_interview_practice_feedback",
    ),
    path(
        "applications/<int:application_id>/ai-cover-letter/",
        views.generate_application_cover_letter_view,
        name="generate_application_cover_letter",
    ),
    path(
        "applications/<int:application_id>/cover-letter.pdf",
        views.download_application_cover_letter_view,
        name="download_application_cover_letter",
    ),
    path(
        "job-postings/<int:job_posting_id>/apply-to/",
        views.update_job_posting_apply_to_view,
        name="update_job_posting_apply_to",
    ),
    path("connections/", views.connections_view, name="connections"),
    path("connections/events/", views.connection_events_view, name="connection_events"),
    path(
        "connections/weekly-total/",
        views.connection_weekly_total_view,
        name="connection_weekly_total",
    ),
    path(
        "connections/events/update/",
        views.update_connection_meeting_view,
        name="update_connection_meeting",
    ),
    path(
        "connections/events/delete/",
        views.delete_connection_view,
        name="delete_connection",
    ),
    path(
        "connections/events/<int:connection_id>/directions/",
        views.connection_directions_view,
        name="connection_directions",
    ),
    path(
        "connections/directions/<int:direction_id>/update/",
        views.update_direction_view,
        name="update_direction",
    ),
    path(
        "connections/directions/<int:direction_id>/delete/",
        views.delete_direction_view,
        name="delete_direction",
    ),
    path("features/", views.features_view, name="features"),
    path("freelancer_search", views.search_view, name="freelancer_search"),
    path("search/save", views.save_freelancer_project_view, name="save_freelancer_project"),
    path("resume/", views.resume_view, name="resume"),
    path("references/", views.references_view, name="references"),
    path("experience/", views.experience_view, name="experience"),
    path("residencies/", views.residencies_view, name="residencies"),
    path("projects/", views.projects_view, name="projects"),
    path("education/", views.courses_view, name="courses"),
]
