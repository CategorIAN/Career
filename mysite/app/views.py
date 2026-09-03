from django.contrib import messages
from django.shortcuts import redirect, render
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F, Prefetch
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from datetime import datetime, UTC
import hashlib
import logging
import re
from django.views.decorators.http import require_POST
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from .forms import (
    PlatformForm,
    PlatformFormSet,
    PlatformSkillFormSet,
    SkillForm,
    SkillFormSet,
)
from .models import (
    Course,
    Platform,
    PlatformSkill,
    Skill,
    Education,
    Residency,
    Role,
    ProfileSetting,
    Project,
    Reference,
    FreelancerProject,
    FreelancerSkill,
    ProjectTask,
    RoleTask,
    Supervisor,
)

from freelancersdk.session import Session
from freelancersdk.resources.projects import search_projects
from freelancersdk.resources.projects.exceptions import ProjectsNotFoundException
from freelancersdk.resources.projects.helpers import create_get_projects_project_details_object


SEARCH_PAGE_SIZE = 10
SEARCH_API_RESULT_LIMIT = 50
SEARCH_CACHE_TIMEOUT = 60 * 60
FREELANCER_RATE_LIMIT_MESSAGE = (
    "Freelancer has temporarily rate-limited project searches. Please try again later."
)


logger = logging.getLogger(__name__)
USER_TIMEZONE = ZoneInfo("America/Denver")


def _join_copy_parts(parts):
    return "\n".join(part for part in parts if part).strip()


def _format_month_year(date_value):
    if not date_value:
        return ""
    return date_value.strftime("%B %Y")


def _format_date_range(start_date, end_date=None, is_current=False):
    start_text = _format_month_year(start_date)
    end_text = "Present" if is_current else _format_month_year(end_date)

    if start_text and end_text:
        return f"{start_text} - {end_text}"
    if start_text:
        return start_text
    return end_text


def _build_date_copy_payload(date_value):
    if not date_value:
        return {
            "display": "",
            "month": "",
            "day": "",
            "year": "",
        }

    return {
        "display": f"{date_value.strftime('%B')} {date_value.day}, {date_value.year}",
        "month": date_value.strftime("%B"),
        "day": str(date_value.day),
        "year": str(date_value.year),
    }


def _format_location_from_company(company):
    return _format_location_from_address(getattr(company, "address", None))


def _format_location_from_address(address):
    city = getattr(address, "city", None) if address else None
    state = getattr(city, "state", None) if city else None

    if city and state:
        return f"{city.name}, {state.abbreviation}"
    if city:
        return city.name
    return ""


def _build_address_copy_payload(address):
    city = getattr(address, "city", None) if address else None
    state = getattr(city, "state", None) if city else None

    street_1 = address.street_1.strip() if address and address.street_1 else ""
    street_2 = address.street_2.strip() if address and address.street_2 else ""
    city_name = city.name.strip() if city and city.name else ""
    state_name = state.name.strip() if state and state.name else ""
    state_code = state.abbreviation.strip() if state and state.abbreviation else ""
    postal_code = address.postal_code.strip() if address and address.postal_code else ""

    return {
        "street_1": street_1,
        "street_2": street_2,
        "city": city_name,
        "state_name": state_name,
        "state": state_code,
        "postal_code": postal_code,
        "location": ", ".join(part for part in [city_name, state_code] if part),
        "full": _join_copy_parts(
            [
                street_1,
                street_2,
                (
                    f"{city_name}, {state_code} {postal_code}".strip()
                    if city_name and state_code
                    else " ".join(
                        part for part in [city_name, state_code, postal_code] if part
                    )
                ),
            ]
        ),
    }


def _build_company_address_copy_payload(company):
    return _build_address_copy_payload(getattr(company, "address", None))


def _format_pay_amount(amount):
    if not amount:
        return ""
    return f"${amount:,.2f}"


def _build_role_copy_payload(role):
    task_lines = [f"- {task.description}" for task in role.tasks.all()]
    skills_text = ", ".join(skill.name for skill in role.skills.all())
    address_payload = _build_company_address_copy_payload(role.company)
    location_text = address_payload["location"]
    date_range = _format_date_range(role.start_date, role.end_date, role.current)
    start_date_payload = _build_date_copy_payload(role.start_date)
    end_date_payload = (
        {
            "display": "Present",
            "month": "",
            "day": "",
            "year": "",
        }
        if role.current
        else _build_date_copy_payload(role.end_date)
    )
    starting_pay = _format_pay_amount(role.starting_pay)
    ending_pay = _format_pay_amount(role.ending_pay)
    pay_frequency = role.get_pay_frequency_display()
    pay_lines = [
        f"Starting pay: {starting_pay}" if starting_pay else "",
        f"Ending pay: {ending_pay}" if ending_pay else "",
        f"Pay frequency: {pay_frequency}" if pay_frequency else "",
    ]
    pay_text = "\n".join(line for line in pay_lines if line)
    supervisor_lines = []

    for supervisor in role.supervisors.all():
        supervisor_parts = [
            supervisor.name,
            supervisor.title,
            supervisor.email,
            supervisor.phone,
        ]
        supervisor_text = " | ".join(part for part in supervisor_parts if part)
        if supervisor_text:
            supervisor_lines.append(supervisor_text)

    supervisors_text = "\n".join(supervisor_lines)

    copy_all = _join_copy_parts(
        [
            role.title,
            role.company.name,
            location_text,
            date_range,
            "",
            f"Description:\n{role.description}" if role.description else "",
            (
                "Responsibilities:\n" + "\n".join(task_lines)
                if task_lines
                else ""
            ),
            f"Skills:\n{skills_text}" if skills_text else "",
            (
                f"Reason for leaving:\n{role.reason_for_leaving}"
                if role.reason_for_leaving
                else ""
            ),
            f"Pay:\n{pay_text}" if pay_text else "",
            f"Supervisors:\n{supervisors_text}" if supervisors_text else "",
        ]
    )

    return {
        "title": role.title,
        "company": role.company.name,
        "street_1": address_payload["street_1"],
        "street_2": address_payload["street_2"],
        "city": address_payload["city"],
        "state_name": address_payload["state_name"],
        "state": address_payload["state"],
        "postal_code": address_payload["postal_code"],
        "address": address_payload["full"],
        "location": location_text,
        "date_range": date_range,
        "start_date": start_date_payload["display"],
        "start_month": start_date_payload["month"],
        "start_day": start_date_payload["day"],
        "start_year": start_date_payload["year"],
        "end_date": end_date_payload["display"],
        "end_month": end_date_payload["month"],
        "end_day": end_date_payload["day"],
        "end_year": end_date_payload["year"],
        "description": role.description.strip(),
        "tasks": "\n".join(task_lines),
        "skills": skills_text,
        "reason_for_leaving": role.reason_for_leaving.strip(),
        "starting_pay": starting_pay,
        "ending_pay": ending_pay,
        "pay_frequency": pay_frequency,
        "pay": pay_text,
        "supervisors": supervisors_text,
        "all": copy_all,
    }


def _build_residency_copy_payload(residency):
    address_payload = _build_address_copy_payload(residency.address)
    location_text = address_payload["location"]
    date_range = _format_date_range(
        residency.start_date,
        residency.end_date,
        residency.current,
    )
    start_date_payload = _build_date_copy_payload(residency.start_date)
    end_date_payload = (
        {
            "display": "Present",
            "month": "",
            "day": "",
            "year": "",
        }
        if residency.current
        else _build_date_copy_payload(residency.end_date)
    )

    copy_all = _join_copy_parts(
        [
            location_text,
            date_range,
            f"Address:\n{address_payload['full']}" if address_payload["full"] else "",
            f"Notes:\n{residency.notes}" if residency.notes else "",
        ]
    )

    return {
        "street_1": address_payload["street_1"],
        "street_2": address_payload["street_2"],
        "city": address_payload["city"],
        "state_name": address_payload["state_name"],
        "state": address_payload["state"],
        "postal_code": address_payload["postal_code"],
        "address": address_payload["full"],
        "location": location_text,
        "date_range": date_range,
        "start_date": start_date_payload["display"],
        "start_month": start_date_payload["month"],
        "start_day": start_date_payload["day"],
        "start_year": start_date_payload["year"],
        "end_date": end_date_payload["display"],
        "end_month": end_date_payload["month"],
        "end_day": end_date_payload["day"],
        "end_year": end_date_payload["year"],
        "notes": residency.notes.strip(),
        "all": copy_all,
    }


def _build_project_copy_payload(project):
    task_lines = [f"- {task.description}" for task in project.tasks.all()]
    skills_text = ", ".join(skill.name for skill in project.skills.all())
    date_range = _format_date_range(project.start_date, project.end_date, not project.end_date)
    start_date_payload = _build_date_copy_payload(project.start_date)
    end_date_payload = (
        {
            "display": "Present",
            "month": "",
            "day": "",
            "year": "",
        }
        if not project.end_date
        else _build_date_copy_payload(project.end_date)
    )

    copy_all = _join_copy_parts(
        [
            project.title,
            date_range,
            "",
            f"Short description:\n{project.short_description}"
            if project.short_description
            else "",
            f"Description:\n{project.description}" if project.description else "",
            f"GitHub URL:\n{project.github_url}" if project.github_url else "",
            f"Live URL:\n{project.live_url}" if project.live_url else "",
            "Tasks:\n" + "\n".join(task_lines) if task_lines else "",
            f"Skills:\n{skills_text}" if skills_text else "",
        ]
    )

    return {
        "title": project.title,
        "date_range": date_range,
        "start_date": start_date_payload["display"],
        "start_month": start_date_payload["month"],
        "start_day": start_date_payload["day"],
        "start_year": start_date_payload["year"],
        "end_date": end_date_payload["display"],
        "end_month": end_date_payload["month"],
        "end_day": end_date_payload["day"],
        "end_year": end_date_payload["year"],
        "short_description": project.short_description.strip(),
        "description": project.description.strip(),
        "github_url": project.github_url.strip(),
        "live_url": project.live_url.strip(),
        "tasks": "\n".join(task_lines),
        "skills": skills_text,
        "all": copy_all,
    }


def _build_course_copy_payload(course):
    education = course.education
    school_name = education.school.name
    program_name = ", ".join(
        part for part in [education.degree, education.field_of_study] if part
    )
    skills_text = ", ".join(skill.name for skill in course.skills.all())

    copy_all = _join_copy_parts(
        [
            course.title,
            f"Course code:\n{course.code}" if course.code else "",
            f"School:\n{school_name}",
            f"Program:\n{program_name}" if program_name else "",
            f"Description:\n{course.description}" if course.description else "",
            f"Grade:\n{course.grade}" if course.grade else "",
            f"Skills:\n{skills_text}" if skills_text else "",
        ]
    )

    return {
        "title": course.title,
        "code": course.code.strip(),
        "school": school_name,
        "program": program_name,
        "description": course.description.strip(),
        "grade": course.grade.strip(),
        "skills": skills_text,
        "all": copy_all,
    }


def home_view(request):
    return render(request, "app/home.html")


def _create_platform_skills_for_platform(platform):
    skills = Skill.objects.all()
    PlatformSkill.objects.bulk_create(
        [
            PlatformSkill(
                platform=platform,
                skill=skill,
            )
            for skill in skills
        ]
    )


def _create_platform_skills_for_skill(skill):
    platforms = Platform.objects.all()
    PlatformSkill.objects.bulk_create(
        [
            PlatformSkill(
                platform=platform,
                skill=skill,
            )
            for platform in platforms
        ]
    )


def skill_formset_view(request):
    selected_skill_id = request.POST.get("skill_id") or request.GET.get("skill_id", "")
    selected_skill_id = selected_skill_id.strip()
    page_number = request.POST.get("page") or request.GET.get("page") or 1
    queryset = Skill.objects.all().order_by(
        F("updated").asc(nulls_first=True),
        "name",
    )
    all_skills = Skill.objects.all().order_by("name", "id")
    selected_skill = None
    is_filtered = False

    if selected_skill_id:
        selected_skill = all_skills.filter(pk=selected_skill_id).first()
        if selected_skill is not None:
            is_filtered = True
            page_queryset = queryset.filter(pk=selected_skill.pk)
            page_obj = None
        else:
            page_queryset = queryset.none()
            page_obj = None
    else:
        paginator = Paginator(queryset, 1)
        page_obj = paginator.get_page(page_number)
        page_queryset = page_obj.object_list

    displayed_skill = selected_skill or page_queryset.first()

    if displayed_skill is not None:
        roles_with_skill = Role.objects.filter(skills=displayed_skill).order_by("title", "id")
        roles_without_skill = Role.objects.exclude(skills=displayed_skill).order_by("title", "id")
    else:
        roles_with_skill = Role.objects.none()
        roles_without_skill = Role.objects.none()

    redirect_params = {}
    if is_filtered:
        redirect_params["skill_id"] = selected_skill_id
    elif page_obj is not None:
        redirect_params["page"] = page_obj.number

    if request.method == "POST":
        new_form = SkillForm(request.POST, prefix="new")
        formset = SkillFormSet(request.POST, queryset=page_queryset)
        add_skill_requested = "add_skill" in request.POST
        delete_skill_id = request.POST.get("delete_skill", "").strip()
        swap_roles_requested = "swap_roles" in request.POST
        invalid_name_message = ""

        if add_skill_requested:
            if new_form.is_valid():
                with transaction.atomic():
                    skill = new_form.save()
                    _create_platform_skills_for_skill(skill)
                return redirect(f"{request.path}?{urlencode({'skill_id': skill.pk})}")
            invalid_name_message = "Invalid Name"
        elif delete_skill_id:
            Skill.objects.filter(pk=delete_skill_id).delete()
            return redirect(request.path)
        elif swap_roles_requested:
            if displayed_skill is not None:
                add_role_ids = [
                    int(key.removeprefix("role_without_skill_"))
                    for key in request.POST
                    if key.startswith("role_without_skill_")
                ]
                remove_role_ids = [
                    int(key.removeprefix("role_with_skill_"))
                    for key in request.POST
                    if key.startswith("role_with_skill_")
                ]

                with transaction.atomic():
                    for role in Role.objects.filter(pk__in=add_role_ids):
                        role.skills.add(displayed_skill)
                    for role in Role.objects.filter(pk__in=remove_role_ids):
                        role.skills.remove(displayed_skill)
            return redirect(f"{request.path}?{urlencode(redirect_params)}")
        else:
            is_formset_valid = formset.is_valid()

            if is_formset_valid:
                with transaction.atomic():
                    current_date = timezone.now().astimezone(USER_TIMEZONE).date()
                    for form in formset.forms:
                        skill = form.save(commit=False)
                        skill.updated = current_date
                        skill.save()
                return redirect(f"{request.path}?{urlencode(redirect_params)}")
    else:
        new_form = SkillForm(prefix="new")
        formset = SkillFormSet(queryset=page_queryset)
        invalid_name_message = ""

    return render(
        request,
        "app/skill_formset.html",
        {
            "new_form": new_form,
            "formset": formset,
            "page_obj": page_obj,
            "all_skills": all_skills,
            "selected_skill": selected_skill,
            "selected_skill_id": selected_skill_id,
            "is_filtered": is_filtered,
            "invalid_name_message": invalid_name_message,
            "roles_with_skill": roles_with_skill,
            "roles_without_skill": roles_without_skill,
        },
    )


def platform_formset_view(request):
    page_number = request.POST.get("page") or request.GET.get("page") or 1
    queryset = Platform.objects.all().order_by("name")
    paginator = Paginator(queryset, 8)
    page_obj = paginator.get_page(page_number)
    page_queryset = page_obj.object_list

    if request.method == "POST":
        new_form = PlatformForm(request.POST, prefix="new")
        formset = PlatformFormSet(request.POST, queryset=page_queryset)
        new_form_has_data = new_form.has_changed()
        is_new_form_valid = new_form.is_valid() if new_form_has_data else True
        is_formset_valid = formset.is_valid()

        if is_formset_valid and is_new_form_valid:
            if new_form_has_data:
                with transaction.atomic():
                    platform = new_form.save()
                    _create_platform_skills_for_platform(platform)
            formset.save()
            return redirect(f"{request.path}?page={page_obj.number}")
    else:
        new_form = PlatformForm(prefix="new")
        formset = PlatformFormSet(queryset=page_queryset)

    return render(
        request,
        "app/platform_formset.html",
        {
            "new_form": new_form,
            "formset": formset,
            "page_obj": page_obj,
        },
    )


def platform_skill_formset_view(request):
    page_number = request.POST.get("page") or request.GET.get("page") or 1
    queryset = PlatformSkill.objects.select_related("platform", "skill").order_by(
        F("updated").asc(nulls_first=True),
        "platform__name",
        "skill__name",
    )
    paginator = Paginator(queryset, 8)
    page_obj = paginator.get_page(page_number)
    page_queryset = page_obj.object_list

    if request.method == "POST":
        formset = PlatformSkillFormSet(request.POST, queryset=page_queryset)
        if formset.is_valid():
            formset.save()
            return redirect(f"{request.path}?page={page_obj.number}")
    else:
        formset = PlatformSkillFormSet(queryset=page_queryset)

    return render(
        request,
        "app/platform_skill_formset.html",
        {
            "formset": formset,
            "page_obj": page_obj,
        },
    )


def _normalize_search_query(query):
    return re.sub(r"\s+", " ", query.strip()).casefold()


def _build_search_cache_key(query):
    normalized_query = _normalize_search_query(query)
    query_hash = hashlib.sha256(normalized_query.encode("utf-8")).hexdigest()
    return f"freelancer-project-search:{query_hash}"


def _build_search_redirect_url(query, page_number=None):
    query_params = {"query": query}
    if page_number:
        query_params["page"] = page_number
    return f"{reverse('search')}?{urlencode(query_params)}"


def _timestamp_to_datetime(timestamp):
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, UTC)


def _get_cached_projects_for_query(query):
    normalized_query = _normalize_search_query(query)
    cache_key = _build_search_cache_key(normalized_query)
    return normalized_query, cache.get(cache_key)


def _get_project_from_cached_results(query, freelancer_project_id):
    normalized_query, cached_projects = _get_cached_projects_for_query(query)
    logger.info(
        "Freelancer project save cache lookup",
        extra={
            "normalized_query": normalized_query,
            "freelancer_project_id": freelancer_project_id,
            "results_from_cache": cached_projects is not None,
        },
    )
    if cached_projects is None:
        return normalized_query, None

    selected_project = next(
        (
            project
            for project in cached_projects
            if str(project.get("id")) == str(freelancer_project_id)
        ),
        None,
    )
    return normalized_query, selected_project


def _save_freelancer_project(project_data):
    freelancer_project_id = project_data["id"]
    budget = project_data.get("budget") or {}
    bid_stats = project_data.get("bid_stats") or {}
    upgrades = project_data.get("upgrades") or {}
    jobs = project_data.get("jobs") or []

    freelancer_project, _ = FreelancerProject.objects.update_or_create(
        freelancer_id=freelancer_project_id,
        defaults={
            "title": project_data.get("title", ""),
            "description": project_data.get("description") or "",
            "status": project_data.get("status", ""),
            "deleted": project_data.get("deleted", False),
            "project_type": project_data.get("type", ""),
            "submitted_at": _timestamp_to_datetime(project_data.get("submitdate")),
            "bid_period_days": project_data.get("bidperiod"),
            "free_bids_expire_at": _timestamp_to_datetime(
                project_data.get("freebids_expire")
            ),
            "budget_min": budget.get("minimum"),
            "budget_max": budget.get("maximum"),
            "bid_count": bid_stats.get("bid_count"),
            "bid_avg": bid_stats.get("bid_avg"),
            "urgent": upgrades.get("urgent", False),
            "featured": upgrades.get("featured", False),
            "nonpublic": upgrades.get("nonpublic", False),
            "enterprise": upgrades.get("enterprise", False),
            "premium": upgrades.get("premium", False),
            "sealed": upgrades.get("sealed", False),
            "nda_required": upgrades.get("NDA", False),
            "raw_json": project_data,
        },
    )

    freelancer_skills = []
    for job in jobs:
        job_id = job.get("id")
        if job_id is None:
            continue

        freelancer_skill, _ = FreelancerSkill.objects.update_or_create(
            id=job_id,
            defaults={
                "name": job.get("name", ""),
                "category_id": job.get("category", {}).get("id"),
                "category_name": job.get("category", {}).get("name"),
            },
        )
        freelancer_skills.append(freelancer_skill)

    freelancer_project.freelancer_skills.set(freelancer_skills)
    return freelancer_project


def _fetch_all_projects_from_api(query):
    session = Session(oauth_token=settings.FREELANCER_TOKEN)
    project_details = create_get_projects_project_details_object(
        full_description=True,
        jobs=True,
    )
    logger.info("Freelancer search API request", extra={"normalized_query": query})
    response = search_projects(
        session,
        query=query,
        project_details=project_details,
        limit=SEARCH_API_RESULT_LIMIT,
        offset=0,
    )
    projects = response.get("projects", [])

    for project in projects:
        submitdate = project.get("submitdate")
        project["submitdate_datetime"] = (
            str(datetime.fromtimestamp(submitdate, UTC).date())
            if submitdate is not None
            else ""
        )

    logger.info(
        "Freelancer search API response",
        extra={
            "normalized_query": query,
            "project_count": len(projects),
        },
    )
    return projects


def _fetch_all_projects(query, force_refresh=False):
    normalized_query = _normalize_search_query(query)
    cache_key = _build_search_cache_key(normalized_query)
    logger.info(
        "Freelancer search cache lookup",
        extra={
            "normalized_query": normalized_query,
            "results_from_cache": not force_refresh,
            "force_refresh": force_refresh,
        },
    )

    if not force_refresh:
        cached_projects = cache.get(cache_key)
        if cached_projects is not None:
            logger.info(
                "Freelancer search cache hit",
                extra={
                    "normalized_query": normalized_query,
                    "results_from_cache": True,
                    "project_count": len(cached_projects),
                },
            )
            return cached_projects, True

    logger.info(
        "Freelancer search cache miss",
        extra={
            "normalized_query": normalized_query,
            "results_from_cache": False,
            "force_refresh": force_refresh,
        },
    )
    projects = _fetch_all_projects_from_api(normalized_query)
    cache.set(cache_key, projects, SEARCH_CACHE_TIMEOUT)
    logger.info(
        "Freelancer search cache store",
        extra={
            "normalized_query": normalized_query,
            "results_from_cache": False,
            "project_count": len(projects),
        },
    )
    return projects, False


def search_view(request):
    if request.method == "POST":
        query = request.POST.get("query", "").strip()
        if not query:
            return redirect(request.path)

        return redirect(f"{request.path}?{urlencode({'query': query})}")

    query = request.GET.get("query", "").strip()
    page_number = request.GET.get("page") or 1
    force_refresh = request.GET.get("refresh") == "1"
    all_projects = []
    page_obj = None
    results_from_cache = False
    search_error_message = ""

    if query:
        try:
            all_projects, results_from_cache = _fetch_all_projects(
                query,
                force_refresh=force_refresh,
            )
        except ProjectsNotFoundException as exc:
            error_message = str(exc)
            if "You have made too many of these requests" in error_message:
                logger.warning(
                    "Freelancer search rate limited",
                    extra={"normalized_query": _normalize_search_query(query)},
                )
                search_error_message = FREELANCER_RATE_LIMIT_MESSAGE
            else:
                raise
        else:
            paginator = Paginator(all_projects, SEARCH_PAGE_SIZE)
            page_obj = paginator.get_page(page_number)
            project_ids = [
                project.get("id")
                for project in page_obj.object_list
                if project.get("id") is not None
            ]
            saved_project_ids = set(
                FreelancerProject.objects.filter(
                    freelancer_id__in=project_ids,
                ).values_list("freelancer_id", flat=True)
            )
            page_projects = [
                {
                    **project,
                    "is_saved": project.get("id") in saved_project_ids,
                }
                for project in page_obj.object_list
            ]
    else:
        page_projects = []

    return render(
        request,
        "app/search.html",
        {
            "query": query,
            "projects": page_projects if page_obj else [],
            "page_obj": page_obj,
            "total_projects": len(all_projects),
            "results_from_cache": results_from_cache,
            "search_error_message": search_error_message,
        }
    )


@require_POST
def save_freelancer_project_view(request):
    freelancer_project_id = request.POST.get("project_id", "").strip()
    query = request.POST.get("query", "").strip()
    page_number = request.POST.get("page", "").strip()
    redirect_url = _build_search_redirect_url(query, page_number or None)

    if not freelancer_project_id or not query:
        messages.error(
            request,
            "The selected Freelancer project could not be saved. Please try the search again.",
        )
        return redirect(redirect_url)

    normalized_query, selected_project = _get_project_from_cached_results(
        query,
        freelancer_project_id,
    )
    if selected_project is None:
        logger.warning(
            "Freelancer project save failed: project not found in cache",
            extra={
                "normalized_query": normalized_query,
                "freelancer_project_id": freelancer_project_id,
            },
        )
        messages.error(
            request,
            "That Freelancer project is no longer available in the cached search results. Please search again.",
        )
        return redirect(redirect_url)

    saved_project = _save_freelancer_project(selected_project)
    logger.info(
        "Freelancer project saved",
        extra={
            "normalized_query": normalized_query,
            "freelancer_project_id": saved_project.freelancer_id,
        },
    )
    messages.success(
        request,
        f'Saved "{saved_project.title}".',
    )
    return redirect(redirect_url)


def resume_view(request):
    profile_settings = ProfileSetting.objects.filter(
        key__in=[
            "location",
            "email",
            "phone",
            "linkedin_url",
            "github_url",
            "resume_summary",
            "platform_summary",
        ]
    )
    profile_by_key = {
        setting.key: setting.value
        for setting in profile_settings
        if setting.value
    }

    roles = (
        Role.objects
        .filter(is_public=True)
        .select_related("company", "company__address", "company__address__city")
        .prefetch_related("tasks")
        .order_by("-start_date")
    )

    projects = (
        Project.objects
        .filter(is_public=True)
        .prefetch_related("tasks")
        .order_by("sort_order", "-start_date", "title")
    )

    education = Education.objects.all().order_by("-end_date")

    skills = Skill.objects.filter(resume_ready=True).order_by(
        "type",
        "-rating",
        "name",
    )

    return render(
        request,
        "app/resume.html",
        {
            "profile": profile_by_key,
            "roles": roles,
            "projects": projects,
            "education": education,
            "skills": skills,
        },
    )


def references_view(request):
    references = (
        Reference.objects
        .select_related(
            "role",
            "role__company",
            "education",
            "education__school",
        )
        .order_by("-preferred", "name")
    )

    return render(
        request,
        "app/references.html",
        {
            "references": references,
        },
    )


def experience_view(request):
    roles = (
        Role.objects
        .select_related(
            "company",
            "company__address",
            "company__address__city",
            "company__address__city__state",
        )
        .prefetch_related(
            Prefetch(
                "tasks",
                queryset=RoleTask.objects.order_by("sort_order", "id"),
            ),
            Prefetch(
                "skills",
                queryset=Skill.objects.order_by("name"),
            ),
            Prefetch(
                "supervisors",
                queryset=Supervisor.objects.order_by("id"),
            ),
        )
        .order_by("-start_date", "-id")
    )

    for role in roles:
        role.copy_payload = _build_role_copy_payload(role)

    return render(
        request,
        "app/experience.html",
        {"roles": roles},
    )


def residencies_view(request):
    residencies = (
        Residency.objects
        .select_related(
            "address",
            "address__city",
            "address__city__state",
        )
        .order_by("-start_date", "-id")
    )

    for residency in residencies:
        residency.copy_payload = _build_residency_copy_payload(residency)

    return render(
        request,
        "app/residencies.html",
        {"residencies": residencies},
    )


def projects_view(request):
    projects = (
        Project.objects
        .prefetch_related(
            Prefetch(
                "tasks",
                queryset=ProjectTask.objects.order_by("sort_order", "id"),
            ),
            Prefetch(
                "skills",
                queryset=Skill.objects.order_by("name"),
            ),
        )
        .order_by("sort_order", "-start_date", "title")
    )

    for project in projects:
        project.copy_payload = _build_project_copy_payload(project)

    return render(
        request,
        "app/projects.html",
        {"projects": projects},
    )


def courses_view(request):
    courses = (
        Course.objects
        .select_related(
            "education",
            "education__school",
        )
        .prefetch_related(
            Prefetch(
                "skills",
                queryset=Skill.objects.order_by("name"),
            ),
        )
        .order_by("sort_order", "title")
    )

    for course in courses:
        course.copy_payload = _build_course_copy_payload(course)

    grouped_courses_by_program = {}
    program_order = []

    for course in courses:
        program_name = course.copy_payload["program"] or "Other"
        if program_name not in grouped_courses_by_program:
            grouped_courses_by_program[program_name] = []
            program_order.append(program_name)
        grouped_courses_by_program[program_name].append(course)

    grouped_courses = [
        {
            "program": program_name,
            "courses": grouped_courses_by_program[program_name],
            "education": grouped_courses_by_program[program_name][0].education,
            "degree": grouped_courses_by_program[program_name][0].education.degree,
            "field_of_study": grouped_courses_by_program[program_name][0].education.field_of_study,
            "start_date_payload": _build_date_copy_payload(
                grouped_courses_by_program[program_name][0].education.start_date
            ),
            "end_date_payload": _build_date_copy_payload(
                grouped_courses_by_program[program_name][0].education.end_date
            ),
            "gpa": (
                str(grouped_courses_by_program[program_name][0].education.gpa)
                if grouped_courses_by_program[program_name][0].education.gpa is not None
                else ""
            ),
            "honors": grouped_courses_by_program[program_name][0].education.honors.strip(),
            "description": grouped_courses_by_program[program_name][0].education.description.strip(),
            "sort_date": max(
                (
                    course.education.end_date
                    or course.education.start_date
                    or course.id
                )
                for course in grouped_courses_by_program[program_name]
            ),
        }
        for program_name in program_order
    ]
    for group in grouped_courses:
        group["date_range"] = _format_date_range(
            group["education"].start_date,
            group["education"].end_date,
            not group["education"].end_date,
        )
        group["start_date"] = group["start_date_payload"]["display"]
        group["start_month"] = group["start_date_payload"]["month"]
        group["start_day"] = group["start_date_payload"]["day"]
        group["start_year"] = group["start_date_payload"]["year"]
        group["end_date"] = (
            "Present" if not group["education"].end_date else group["end_date_payload"]["display"]
        )
        group["end_month"] = "" if not group["education"].end_date else group["end_date_payload"]["month"]
        group["end_day"] = "" if not group["education"].end_date else group["end_date_payload"]["day"]
        group["end_year"] = "" if not group["education"].end_date else group["end_date_payload"]["year"]
    grouped_courses.sort(key=lambda group: group["sort_date"], reverse=True)

    return render(
        request,
        "app/courses.html",
        {
            "courses": courses,
            "course_groups": grouped_courses,
        },
    )
