from django.urls import path
from . import views

urlpatterns = [
    path("skills/", views.skill_formset_view, name="skills"),
    path("search", views.search_view, name="search")
]