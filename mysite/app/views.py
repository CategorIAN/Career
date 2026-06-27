from django.shortcuts import redirect, render
from django.core.paginator import Paginator
from django.db.models import F
from django.conf import settings
from datetime import datetime, UTC
from urllib.parse import urlencode

from .forms import SkillForm, SkillFormSet
from .models import Skill

from freelancersdk.session import Session
from freelancersdk.resources.projects import search_projects
from freelancersdk.resources.projects.helpers import create_get_projects_project_details_object


SEARCH_PAGE_SIZE = 10
SEARCH_API_BATCH_SIZE = 100


def home_view(request):
    return render(request, "app/home.html")


def skill_formset_view(request):
    page_number = request.POST.get("page") or request.GET.get("page") or 1
    queryset = Skill.objects.all().order_by(
        F("updated").asc(nulls_first=True),
        "name",
    )
    paginator = Paginator(queryset, 8)
    page_obj = paginator.get_page(page_number)
    page_queryset = page_obj.object_list

    if request.method == "POST":
        new_form = SkillForm(request.POST, prefix="new")
        formset = SkillFormSet(request.POST, queryset=page_queryset)
        new_form_has_data = new_form.has_changed()
        is_new_form_valid = new_form.is_valid() if new_form_has_data else True
        is_formset_valid = formset.is_valid()

        if is_new_form_valid and new_form_has_data:
            new_form.save()

        if is_formset_valid and is_new_form_valid:
            formset.save()
            return redirect(f"{request.path}?page={page_obj.number}")
    else:
        new_form = SkillForm(prefix="new")
        formset = SkillFormSet(queryset=page_queryset)

    return render(
        request,
        "app/skill_formset.html",
        {
            "new_form": new_form,
            "formset": formset,
            "page_obj": page_obj,
        },
    )


def _fetch_all_projects(query):
    session = Session(oauth_token=settings.FREELANCER_TOKEN)
    project_details = create_get_projects_project_details_object(
        full_description=True,
        jobs=True,
    )
    projects = []
    offset = 0

    while True:
        response = search_projects(
            session,
            query=query,
            project_details=project_details,
            limit=SEARCH_API_BATCH_SIZE,
            offset=offset,
        )
        batch = response.get("projects", [])

        if not batch:
            break

        projects.extend(batch)

        if len(batch) < SEARCH_API_BATCH_SIZE:
            break

        offset += SEARCH_API_BATCH_SIZE

    for project in projects:
        project["submitdate_datetime"] = str(datetime.fromtimestamp(
            project["submitdate"],
            UTC,
        ).date())

    return projects


def search_view(request):
    if request.method == "POST":
        query = request.POST.get("query", "").strip()
        if not query:
            return redirect(request.path)

        return redirect(f"{request.path}?{urlencode({'query': query})}")

    query = request.GET.get("query", "").strip()
    page_number = request.GET.get("page") or 1
    all_projects = []
    page_obj = None

    if query:
        all_projects = _fetch_all_projects(query)
        paginator = Paginator(all_projects, SEARCH_PAGE_SIZE)
        page_obj = paginator.get_page(page_number)

    return render(
        request,
        "app/search.html",
        {
            "query": query,
            "projects": page_obj.object_list if page_obj else [],
            "page_obj": page_obj,
            "total_projects": len(all_projects),
        }
    )
