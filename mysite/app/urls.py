from django.urls import path
from . import views

urlpatterns = [
    path("", views.home_view, name="home"),
    path("skills/", views.skill_formset_view, name="skills"),
    path("search", views.search_view, name="search"),
    path("search/save", views.save_freelancer_project_view, name="save_freelancer_project"),
    path("resume/", views.resume_view, name="resume"),
    path("references/", views.references_view, name="references"),
    path("experience/", views.experience_view, name="experience"),
    path("residencies/", views.residencies_view, name="residencies"),
    path("projects/", views.projects_view, name="projects"),
    path("education/", views.courses_view, name="courses"),
]
