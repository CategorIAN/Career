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
