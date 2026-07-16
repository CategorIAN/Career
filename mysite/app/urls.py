from django.urls import path
from . import views

urlpatterns = [
    path("", views.home_view, name="home"),
    path("skills/", views.skill_formset_view, name="skills"),
    path("search", views.search_view, name="search"),
    path("resume/", views.resume_view, name="resume"),
]
