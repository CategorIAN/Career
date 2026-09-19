from unittest.mock import MagicMock, patch
import json
from io import StringIO

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.contrib.messages import get_messages
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from freelancersdk.resources.projects.exceptions import ProjectsNotFoundException

from .models import (
    Address,
    City,
    Company,
    Country,
    Course,
    Direction,
    Education,
    Feature,
    FeatureLink,
    FreelancerProject,
    FreelancerSkill,
    JobPosting,
    Platform,
    PlatformSkill,
    Professional,
    ProfessionalConnect,
    Recruiter,
    Connect,
    Project,
    ProjectTask,
    Residency,
    Role,
    RoleTask,
    SearchObservation,
    SearchPath,
    SearchTerm,
    School,
    Skill,
    State,
    Supervisor,
    PlatformFeature,
)
from .views import (
    FREELANCER_RATE_LIMIT_MESSAGE,
    SEARCH_API_RESULT_LIMIT,
    _build_search_cache_key,
    _normalize_search_query,
)
from .services.google_calendar import sync_meeting_event, sync_professional_connect


def make_project(
    project_id,
    *,
    title=None,
    submitdate=1721260800,
    jobs=None,
    upgrades=None,
    freebids_expire=1721347200,
):
    return {
        "id": project_id,
        "title": title or f"Project {project_id}",
        "description": f"Description {project_id}",
        "status": "active",
        "deleted": False,
        "type": "fixed",
        "budget": {"minimum": 10, "maximum": 20},
        "currency": {"sign": "$", "code": "USD"},
        "bid_stats": {"bid_count": 3, "bid_avg": 15},
        "jobs": jobs if jobs is not None else [{"id": 11, "name": "Python"}],
        "submitdate": submitdate,
        "bidperiod": 7,
        "freebids_expire": freebids_expire,
        "upgrades": upgrades
        if upgrades is not None
        else {
            "urgent": False,
            "featured": False,
            "nonpublic": False,
            "enterprise": False,
            "premium": False,
            "sealed": False,
            "NDA": False,
        },
    }


class FreelancerSearchViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.search_url = reverse("freelancer_search")
        self.save_url = reverse("save_freelancer_project")

    def test_freelancer_search_uses_renamed_path(self):
        self.assertEqual(self.search_url, "/freelancer_search")

    @patch("app.views.search_projects")
    def test_single_api_call_then_local_pagination_uses_cache(self, mock_search_projects):
        mock_search_projects.return_value = {
            "projects": [make_project(project_id) for project_id in range(1, 16)]
        }

        response = self.client.get(self.search_url, {"query": "  Python   Developer  "})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_search_projects.call_count, 1)
        self.assertFalse(response.context["results_from_cache"])
        self.assertEqual(len(response.context["projects"]), 10)

        _, kwargs = mock_search_projects.call_args
        self.assertEqual(kwargs["offset"], 0)
        self.assertEqual(kwargs["limit"], SEARCH_API_RESULT_LIMIT)
        self.assertIn("submitdate_datetime", response.context["projects"][0])

        cached_response = self.client.get(
            self.search_url,
            {"query": "python developer", "page": 2},
        )

        self.assertEqual(cached_response.status_code, 200)
        self.assertEqual(mock_search_projects.call_count, 1)
        self.assertTrue(cached_response.context["results_from_cache"])
        self.assertEqual(cached_response.context["page_obj"].number, 2)
        self.assertEqual(len(cached_response.context["projects"]), 5)

    @patch("app.views.search_projects")
    def test_refresh_replaces_cached_results_with_one_api_call(self, mock_search_projects):
        mock_search_projects.side_effect = [
            {"projects": [make_project(1)]},
            {"projects": [make_project(2)]},
        ]

        first_response = self.client.get(self.search_url, {"query": "python"})
        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(mock_search_projects.call_count, 1)
        self.assertEqual(first_response.context["projects"][0]["id"], 1)

        refresh_response = self.client.get(
            self.search_url,
            {"query": "python", "refresh": 1},
        )

        self.assertEqual(refresh_response.status_code, 200)
        self.assertEqual(mock_search_projects.call_count, 2)
        self.assertFalse(refresh_response.context["results_from_cache"])
        self.assertEqual(refresh_response.context["projects"][0]["id"], 2)

        cached_response = self.client.get(self.search_url, {"query": "python"})
        self.assertEqual(cached_response.status_code, 200)
        self.assertEqual(mock_search_projects.call_count, 2)
        self.assertTrue(cached_response.context["results_from_cache"])
        self.assertEqual(cached_response.context["projects"][0]["id"], 2)

    @patch("app.views.search_projects")
    def test_rate_limited_projects_not_found_shows_friendly_message_and_is_not_cached(
        self,
        mock_search_projects,
    ):
        mock_search_projects.side_effect = ProjectsNotFoundException(
            "You have made too many of these requests",
            "429",
            "req-1",
        )

        response = self.client.get(self.search_url, {"query": "python"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, FREELANCER_RATE_LIMIT_MESSAGE)
        self.assertEqual(response.context["projects"], [])
        self.assertFalse(response.context["results_from_cache"])

        normalized_query = _normalize_search_query("python")
        cache_key = _build_search_cache_key(normalized_query)
        self.assertIsNone(cache.get(cache_key))

    def test_save_view_creates_project_and_skills_from_cached_results(self):
        normalized_query = _normalize_search_query("Python Search")
        cache.set(
            _build_search_cache_key(normalized_query),
            [
                make_project(
                    101,
                    jobs=[
                        {"id": 11, "name": "Python", "category": {"id": 2, "name": "Languages"}},
                        {"id": 12, "name": "Django", "category": {"id": 3, "name": "Frameworks"}},
                    ],
                    upgrades={
                        "urgent": True,
                        "featured": True,
                        "nonpublic": True,
                        "enterprise": False,
                        "premium": True,
                        "sealed": False,
                        "NDA": True,
                    },
                )
            ],
            3600,
        )

        response = self.client.post(
            self.save_url,
            {"project_id": "101", "query": "Python Search", "page": "2"},
        )

        self.assertRedirects(response, f"{self.search_url}?query=Python+Search&page=2")

        saved_project = FreelancerProject.objects.get(freelancer_id=101)
        self.assertEqual(saved_project.title, "Project 101")
        self.assertEqual(saved_project.project_type, "fixed")
        self.assertEqual(saved_project.bid_count, 3)
        self.assertEqual(str(saved_project.bid_avg), "15.00")
        self.assertEqual(str(saved_project.budget_min), "10.00")
        self.assertEqual(str(saved_project.budget_max), "20.00")
        self.assertTrue(saved_project.urgent)
        self.assertTrue(saved_project.featured)
        self.assertTrue(saved_project.nonpublic)
        self.assertTrue(saved_project.premium)
        self.assertTrue(saved_project.nda_required)
        self.assertIsNotNone(saved_project.submitted_at)
        self.assertIsNotNone(saved_project.free_bids_expire_at)
        self.assertEqual(saved_project.raw_json["id"], 101)

        saved_skill_ids = set(
            saved_project.freelancer_skills.values_list("id", flat=True)
        )
        self.assertEqual(saved_skill_ids, {11, 12})
        self.assertTrue(FreelancerSkill.objects.filter(id=11, name="Python").exists())
        self.assertTrue(FreelancerSkill.objects.filter(id=12, name="Django").exists())

        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(str(messages[0]), 'Saved "Project 101".')

    def test_save_view_updates_existing_project_and_synchronizes_skills(self):
        old_skill = FreelancerSkill.objects.create(id=21, name="Old Skill")
        project = FreelancerProject.objects.create(
            freelancer_id=202,
            title="Old Title",
            description="Old Description",
            status="pending",
            deleted=False,
            project_type="hourly",
        )
        project.freelancer_skills.set([old_skill])

        normalized_query = _normalize_search_query("python")
        cache.set(
            _build_search_cache_key(normalized_query),
            [
                make_project(
                    202,
                    title="Updated Title",
                    jobs=[
                        {"id": 22, "name": "New Skill", "category": {"id": 4, "name": "Tools"}},
                    ],
                )
            ],
            3600,
        )

        response = self.client.post(
            self.save_url,
            {"project_id": "202", "query": "python", "page": "1"},
        )

        self.assertRedirects(response, f"{self.search_url}?query=python&page=1")

        project.refresh_from_db()
        self.assertEqual(project.title, "Updated Title")
        self.assertEqual(
            list(project.freelancer_skills.values_list("id", flat=True)),
            [22],
        )

    def test_save_view_shows_friendly_error_when_project_missing_from_cache(self):
        normalized_query = _normalize_search_query("python")
        cache.set(
            _build_search_cache_key(normalized_query),
            [make_project(301)],
            3600,
        )

        response = self.client.post(
            self.save_url,
            {"project_id": "999", "query": "python", "page": "3"},
        )

        self.assertRedirects(response, f"{self.search_url}?query=python&page=3")
        self.assertFalse(FreelancerProject.objects.exists())

        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(
            str(messages[0]),
            "That Freelancer project is no longer available in the cached search results. Please search again.",
        )

    def test_search_results_show_saved_indicator_for_existing_projects(self):
        FreelancerProject.objects.create(
            freelancer_id=401,
            title="Saved Project",
            description="Saved description",
            status="active",
            deleted=False,
            project_type="fixed",
        )

        normalized_query = _normalize_search_query("python")
        cache.set(
            _build_search_cache_key(normalized_query),
            [make_project(401), make_project(402)],
            3600,
        )

        response = self.client.get(self.search_url, {"query": "python"})

        self.assertEqual(response.status_code, 200)
        projects_by_id = {project["id"]: project for project in response.context["projects"]}
        self.assertTrue(projects_by_id[401]["is_saved"])
        self.assertFalse(projects_by_id[402]["is_saved"])
        self.assertContains(response, "Saved")
        self.assertContains(response, 'name="project_id" value="402"', html=False)


class ApplicationReferencePageTests(TestCase):
    def setUp(self):
        self.country = Country.objects.create(name="United States", code="USA")
        self.state = State.objects.create(
            name="Montana",
            abbreviation="MT",
            country=self.country,
        )
        self.city = City.objects.create(name="Helena", state=self.state)
        self.address = Address.objects.create(
            street_1="1 Main St",
            street_2="Suite 200",
            city=self.city,
            postal_code="59601",
        )
        self.company = Company.objects.create(
            name="Carroll College",
            address=self.address,
            website="https://www.carroll.edu",
            phone="406-447-4300",
        )
        self.school = School.objects.create(name="State University", city=self.city)
        self.education = Education.objects.create(
            school=self.school,
            degree="Master of Science",
            field_of_study="Data Science",
            start_date="2023-08-15",
            end_date="2025-05-20",
            gpa="3.95",
            honors="Graduate Honors",
            description="Focused on advanced analytics and machine learning.",
        )
        self.python_skill = Skill.objects.create(name="Python", type="Language")
        self.sql_skill = Skill.objects.create(name="SQL", type="Technology")
        self.research_skill = Skill.objects.create(name="Research", type="Domain")

    def test_experience_page_uses_complete_role_data_and_hides_supervisors(self):
        earlier_role = Role.objects.create(
            company=self.company,
            title="Analyst",
            start_date="2022-01-01",
            end_date="2023-01-01",
            description="Earlier role description.",
        )
        role = Role.objects.create(
            company=self.company,
            title="Assistant Director of Institutional Research",
            start_date="2024-08-01",
            end_date="2026-03-01",
            description="Led reporting and analytics projects.",
            reason_for_leaving="Position ended.",
            starting_pay="0.00",
            ending_pay="72000.00",
            pay_frequency=Role.PayFrequency.MONTHLY,
        )
        role.skills.set([self.sql_skill, self.python_skill])
        RoleTask.objects.create(role=role, description="Second task", sort_order=2)
        RoleTask.objects.create(role=role, description="First task", sort_order=1)
        Supervisor.objects.create(
            role=role,
            name="Supervisor Name",
            title="Director",
            email="boss@example.com",
            phone="555-123-4567",
        )

        response = self.client.get(reverse("experience"))

        self.assertEqual(response.status_code, 200)
        roles = list(response.context["roles"])
        self.assertEqual([item.pk for item in roles], [role.pk, earlier_role.pk])
        self.assertContains(response, "https://www.carroll.edu")
        self.assertContains(response, 'href="https://www.carroll.edu"')
        self.assertContains(response, "406-447-4300")
        self.assertContains(response, 'id="role-website-')
        self.assertContains(response, 'id="role-phone-')
        self.assertContains(response, "1 Main St")
        self.assertContains(response, "Suite 200")
        self.assertContains(response, ">City<", html=False)
        self.assertContains(response, "Montana")
        self.assertContains(response, ">State<", html=False)
        self.assertContains(response, "59601")
        self.assertContains(response, "Copy Address")
        self.assertContains(response, "Show Address")
        self.assertNotContains(response, "Copy Location")
        self.assertNotContains(response, "Helena, MT")
        self.assertContains(response, 'id="role-street-1-')
        self.assertContains(response, 'id="role-street-2-')
        self.assertContains(response, 'id="role-city-')
        self.assertContains(response, 'id="role-state-name-')
        self.assertContains(response, 'id="role-postal-code-')
        self.assertContains(response, "August 2024 - March 2026")
        self.assertContains(response, "Show Dates")
        self.assertContains(response, "August 1, 2024")
        self.assertContains(response, "March 1, 2026")
        self.assertContains(response, 'id="role-start-month-')
        self.assertContains(response, 'id="role-start-day-')
        self.assertContains(response, 'id="role-start-year-')
        self.assertContains(response, 'id="role-end-month-')
        self.assertContains(response, 'id="role-end-day-')
        self.assertContains(response, 'id="role-end-year-')
        self.assertContains(response, "Led reporting and analytics projects.")
        self.assertContains(response, "<li>First task</li>", html=True)
        self.assertContains(response, "<li>Second task</li>", html=True)
        self.assertContains(response, "Python, SQL")
        self.assertContains(response, 'class="utility-skill-grid"')
        self.assertContains(response, 'id="role-skill-')
        self.assertContains(response, "Position ended.")
        self.assertContains(response, "Ending pay: $72,000.00")
        self.assertContains(response, "Pay frequency: Monthly")
        self.assertNotContains(response, "Starting pay: $0.00")
        self.assertContains(response, "Supervisor Name")
        self.assertContains(response, "boss@example.com")
        self.assertContains(response, "555-123-4567")
        self.assertContains(response, 'class="copy-button supervisor-toggle-button"')
        self.assertContains(response, 'id="role-supervisor-details-')
        self.assertContains(response, 'id="role-supervisor-')
        self.assertContains(response, 'id="role-supervisor-title-')
        self.assertContains(response, 'id="role-supervisor-email-')
        self.assertContains(response, 'id="role-supervisor-phone-')
        self.assertContains(response, "Description:\nLed reporting and analytics projects.", html=False)
        self.assertContains(response, "Responsibilities:\n- First task\n- Second task", html=False)
        self.assertContains(response, "Skills:\nPython, SQL", html=False)
        self.assertContains(
            response,
            "Website: https://www.carroll.edu\nPhone: 406-447-4300",
            html=False,
        )
        self.assertContains(
            response,
            "Pay:\nEnding pay: $72,000.00\nPay frequency: Monthly",
            html=False,
        )
        self.assertContains(
            response,
            "Supervisor Name | Director | boss@example.com | 555-123-4567",
            html=False,
        )

    def test_residencies_page_shows_reverse_chronological_address_history(self):
        earlier_residency = Residency.objects.create(
            address=self.address,
            start_date="2022-01-01",
            end_date="2024-01-01",
            notes="Earlier residence.",
        )
        newer_residency = Residency.objects.create(
            address=self.address,
            start_date="2024-08-01",
            end_date="2026-03-01",
            notes="Most recent residence.",
        )

        response = self.client.get(reverse("residencies"))

        self.assertEqual(response.status_code, 200)
        residencies = list(response.context["residencies"])
        self.assertEqual([item.pk for item in residencies], [newer_residency.pk, earlier_residency.pk])
        self.assertContains(response, "Residence history in reverse chronological order")
        self.assertContains(response, "Copy All")
        self.assertContains(response, "Show Address")
        self.assertContains(response, "Show Dates")
        self.assertContains(response, "Copy Address")
        self.assertContains(response, "1 Main St")
        self.assertContains(response, "Suite 200")
        self.assertContains(response, ">City<", html=False)
        self.assertContains(response, "Montana")
        self.assertContains(response, ">State<", html=False)
        self.assertContains(response, "59601")
        self.assertContains(response, 'id="residency-street-1-')
        self.assertContains(response, 'id="residency-street-2-')
        self.assertContains(response, 'id="residency-city-')
        self.assertContains(response, 'id="residency-state-name-')
        self.assertContains(response, 'id="residency-postal-code-')
        self.assertContains(response, "August 2024 - March 2026")
        self.assertContains(response, "August 1, 2024")
        self.assertContains(response, "March 1, 2026")
        self.assertContains(response, 'id="residency-start-month-')
        self.assertContains(response, 'id="residency-start-day-')
        self.assertContains(response, 'id="residency-start-year-')
        self.assertContains(response, 'id="residency-end-month-')
        self.assertContains(response, 'id="residency-end-day-')
        self.assertContains(response, 'id="residency-end-year-')
        self.assertContains(response, "Most recent residence.")
        self.assertContains(response, "Address:\n1 Main St\nSuite 200\nHelena, MT 59601", html=False)
        self.assertContains(response, "Notes:\nMost recent residence.", html=False)

    def test_projects_page_uses_ordered_tasks_and_complete_project_fields(self):
        project = Project.objects.create(
            title="Career Portal",
            short_description="A concise summary.",
            description="A longer project description.",
            start_date="2025-01-01",
            end_date="2025-06-01",
            resume_ready=False,
            github_url="https://github.com/example/career-portal",
            live_url="https://career.example.com",
            sort_order=2,
        )
        earlier_project = Project.objects.create(
            title="Earlier Project",
            sort_order=1,
        )
        project.skills.set([self.sql_skill, self.python_skill])
        ProjectTask.objects.create(project=project, description="Second project task", sort_order=2)
        ProjectTask.objects.create(project=project, description="First project task", sort_order=1)

        response = self.client.get(reverse("projects"))

        self.assertEqual(response.status_code, 200)
        projects = list(response.context["projects"])
        self.assertEqual([item.pk for item in projects], [earlier_project.pk, project.pk])
        self.assertContains(response, 'id="project-details-')
        self.assertContains(response, ">Show<", html=False)
        self.assertContains(response, "January 2025 - June 2025")
        self.assertContains(response, "Show Dates")
        self.assertContains(response, "January 1, 2025")
        self.assertContains(response, "June 1, 2025")
        self.assertContains(response, 'id="project-start-month-')
        self.assertContains(response, 'id="project-start-day-')
        self.assertContains(response, 'id="project-start-year-')
        self.assertContains(response, 'id="project-end-month-')
        self.assertContains(response, 'id="project-end-day-')
        self.assertContains(response, 'id="project-end-year-')
        self.assertContains(response, "A concise summary.")
        self.assertContains(response, "A longer project description.")
        self.assertContains(response, "https://github.com/example/career-portal")
        self.assertContains(response, "https://career.example.com")
        self.assertContains(response, "<li>First project task</li>", html=True)
        self.assertContains(response, "<li>Second project task</li>", html=True)
        self.assertContains(response, "Python, SQL")
        self.assertContains(response, 'class="utility-skill-grid"')
        self.assertContains(response, 'id="project-skill-')
        self.assertContains(response, "Short description:\nA concise summary.", html=False)
        self.assertContains(response, "Tasks:\n- First project task\n- Second project task", html=False)

    def test_courses_page_uses_sort_order_and_related_education(self):
        later_course = Course.objects.create(
            education=self.education,
            title="Advanced Analytics",
            code="DS 610",
            description="Applied analytics course.",
            grade="A",
            sort_order=2,
        )
        earlier_course = Course.objects.create(
            education=self.education,
            title="Intro to Data",
            code="DS 500",
            sort_order=1,
        )
        later_course.skills.set([self.research_skill, self.python_skill])

        response = self.client.get(reverse("courses"))

        self.assertEqual(response.status_code, 200)
        courses = list(response.context["courses"])
        course_groups = response.context["course_groups"]
        self.assertEqual([item.pk for item in courses], [earlier_course.pk, later_course.pk])
        self.assertEqual(len(course_groups), 1)
        self.assertEqual(course_groups[0]["program"], "Master of Science, Data Science")
        self.assertEqual(course_groups[0]["degree"], "Master of Science")
        self.assertEqual(course_groups[0]["field_of_study"], "Data Science")
        self.assertEqual(course_groups[0]["date_range"], "August 2023 - May 2025")
        self.assertEqual(course_groups[0]["start_date"], "August 15, 2023")
        self.assertEqual(course_groups[0]["end_date"], "May 20, 2025")
        self.assertEqual(course_groups[0]["gpa"], "3.95")
        self.assertEqual(course_groups[0]["honors"], "Graduate Honors")
        self.assertEqual(
            course_groups[0]["description"],
            "Focused on advanced analytics and machine learning.",
        )
        self.assertEqual(
            [item.pk for item in course_groups[0]["courses"]],
            [earlier_course.pk, later_course.pk],
        )
        self.assertContains(response, 'class="copy-button course-group-toggle-button"')
        self.assertContains(response, 'id="course-group-')
        self.assertContains(response, 'class="copy-button course-list-toggle-button"')
        self.assertContains(response, 'id="course-list-')
        self.assertContains(response, ">Courses<", html=False)
        self.assertContains(response, 'id="course-details-')
        self.assertContains(response, 'id="program-school-')
        self.assertContains(response, "Helena")
        self.assertContains(response, "Montana")
        self.assertContains(response, 'id="program-city-')
        self.assertContains(response, 'id="program-state-')
        self.assertContains(response, ">Show<", html=False)
        self.assertContains(response, "DS 610")
        self.assertContains(response, "State University")
        self.assertContains(response, "Master of Science, Data Science")
        self.assertContains(response, "Master of Science")
        self.assertContains(response, "Data Science")
        self.assertContains(response, "August 2023 - May 2025")
        self.assertContains(response, "August 15, 2023")
        self.assertContains(response, "May 20, 2025")
        self.assertContains(response, "3.95")
        self.assertContains(response, "Graduate Honors")
        self.assertContains(response, "Show Dates")
        self.assertContains(response, 'id="program-degree-')
        self.assertContains(response, 'id="program-field-of-study-')
        self.assertContains(response, 'id="program-gpa-')
        self.assertContains(response, 'id="program-honors-')
        self.assertContains(response, 'id="program-description-')
        self.assertContains(response, 'id="program-start-month-')
        self.assertContains(response, 'id="program-start-day-')
        self.assertContains(response, 'id="program-start-year-')
        self.assertContains(response, 'id="program-end-month-')
        self.assertContains(response, 'id="program-end-day-')
        self.assertContains(response, 'id="program-end-year-')
        self.assertContains(
            response,
            "Focused on advanced analytics and machine learning.",
        )
        self.assertContains(response, "Applied analytics course.")
        self.assertContains(response, "A")
        self.assertContains(response, "Python, Research")
        self.assertContains(response, 'class="utility-skill-grid"')
        self.assertContains(response, 'id="course-skill-')
        self.assertContains(response, "Program:\nMaster of Science, Data Science", html=False)


class PlatformPageTests(TestCase):
    def test_platforms_page_shows_add_delete_column_and_buttons(self):
        platform = Platform.objects.create(
            name="Alpha Platform",
            url="https://alpha.example.com",
            max_skills=10,
        )

        response = self.client.get(reverse("platforms"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<title>Platforms</title>", html=False)
        self.assertContains(response, "<h1>Platforms</h1>", html=False)
        self.assertContains(response, "Add/Delete")
        self.assertContains(response, "Job Search Enabled")
        self.assertContains(response, 'name="form-0-job_search_enabled"', html=False)
        self.assertContains(response, 'name="add_platform" value="1"', html=False)
        self.assertContains(response, f'name="delete_platform" value="{platform.pk}"', html=False)
        self.assertNotContains(response, 'name="form-0-DELETE"', html=False)
        self.assertNotContains(response, ">New<", html=False)

    def test_platforms_save_updates_existing_rows_without_creating_top_row(self):
        existing_platform = Platform.objects.create(
            name="Alpha Platform",
            url="https://alpha.example.com",
            max_skills=10,
        )

        response = self.client.post(
            reverse("platforms"),
            data={
                "form-TOTAL_FORMS": "1",
                "form-INITIAL_FORMS": "1",
                "form-MIN_NUM_FORMS": "0",
                "form-MAX_NUM_FORMS": "1000",
                "page": "1",
                "form-0-id": str(existing_platform.pk),
                "form-0-name": "Alpha Platform Updated",
                "form-0-url": "https://updated.example.com",
                "form-0-max_skills": "12",
                "form-0-job_search_enabled": "on",
                "new-name": "Should Not Save",
                "new-url": "https://ignored.example.com",
                "new-max_skills": "3",
            },
        )

        self.assertRedirects(response, f"{reverse('platforms')}?page=1")
        existing_platform.refresh_from_db()
        self.assertEqual(existing_platform.name, "Alpha Platform Updated")
        self.assertEqual(existing_platform.url, "https://updated.example.com")
        self.assertEqual(existing_platform.max_skills, 12)
        self.assertTrue(existing_platform.job_search_enabled)
        self.assertFalse(Platform.objects.filter(name="Should Not Save").exists())

    def test_platforms_add_button_creates_platform(self):
        skill = Skill.objects.create(name="Python", type="Language")
        first_feature = Feature.objects.create(name="Auth")
        second_feature = Feature.objects.create(name="Billing")

        response = self.client.post(
            reverse("platforms"),
            data={
                "form-TOTAL_FORMS": "0",
                "form-INITIAL_FORMS": "0",
                "form-MIN_NUM_FORMS": "0",
                "form-MAX_NUM_FORMS": "1000",
                "page": "1",
                "new-name": "Beta Platform",
                "new-url": "https://beta.example.com",
                "new-max_skills": "5",
                "add_platform": "1",
            },
        )

        created_platform = Platform.objects.get(name="Beta Platform")
        self.assertRedirects(response, f"{reverse('platforms')}?page=1")
        self.assertEqual(created_platform.url, "https://beta.example.com")
        self.assertEqual(created_platform.max_skills, 5)
        self.assertTrue(
            PlatformSkill.objects.filter(platform=created_platform, skill=skill).exists()
        )
        self.assertEqual(
            set(
                PlatformFeature.objects.filter(platform=created_platform).values_list(
                    "feature_id",
                    flat=True,
                )
            ),
            {first_feature.pk, second_feature.pk},
        )

    def test_platforms_delete_button_removes_existing_platform(self):
        platform = Platform.objects.create(
            name="Alpha Platform",
            url="https://alpha.example.com",
            max_skills=10,
        )

        response = self.client.post(
            reverse("platforms"),
            data={
                "form-TOTAL_FORMS": "1",
                "form-INITIAL_FORMS": "1",
                "form-MIN_NUM_FORMS": "0",
                "form-MAX_NUM_FORMS": "1000",
                "page": "1",
                "form-0-id": str(platform.pk),
                "form-0-name": platform.name,
                "form-0-url": platform.url,
                "form-0-max_skills": str(platform.max_skills),
                "delete_platform": str(platform.pk),
            },
        )

        self.assertRedirects(response, f"{reverse('platforms')}?page=1")
        self.assertFalse(Platform.objects.filter(pk=platform.pk).exists())


class ProfessionalPageTests(TestCase):
    def test_professional_reverse_connections_use_professional_relation(self):
        professional = Professional.objects.create(name="Ada Lovelace")
        connection = ProfessionalConnect.objects.create(
            professional=professional,
            invite_date=date(2026, 9, 12),
        )

        response = self.client.get(
            reverse("professionals"),
            {"professional_id": professional.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(professional.connects.all()), [connection])
        self.assertContains(response, "Ada Lovelace")

    def test_professionals_page_shows_modal_add_form_and_existing_cards(self):
        professional = Professional.objects.create(
            name="Ada Lovelace",
            linkedin_url="https://www.linkedin.com/in/ada-lovelace",
            email="ada@example.com",
            wait=timedelta(days=15),
        )

        response = self.client.get(reverse("professionals"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<title>Professionals</title>", html=False)
        self.assertContains(response, "Add Professional")
        self.assertContains(response, "Professional 1 of 1")
        self.assertContains(response, 'id="professional-add-modal"', html=False)
        self.assertContains(response, 'data-target="professional-add-modal"', html=False)
        self.assertContains(response, 'class="close-professional-modal"', html=False)
        self.assertContains(response, '<table class="project-results">', html=False)
        self.assertContains(response, "<th>Name</th>", html=False)
        self.assertContains(response, "<th>Wait</th>", html=False)
        self.assertContains(response, "<th>Average Rating</th>", html=False)
        self.assertContains(response, "<th>Invite Success</th>", html=False)
        self.assertContains(response, "<th>Invite Due</th>", html=False)
        self.assertContains(response, "<th>Connect Due</th>", html=False)
        self.assertContains(response, "<th>Invite</th>", html=False)
        self.assertContains(response, "<th>Send Invite</th>", html=False)
        self.assertContains(response, "<th>Pass</th>", html=False)
        self.assertContains(response, "<th>Edit</th>", html=False)
        self.assertContains(response, 'name="new-name"', html=False)
        self.assertContains(response, 'name="new-linkedin_url"', html=False)
        self.assertContains(response, 'name="new-email"', html=False)
        self.assertContains(response, 'name="new-phone"', html=False)
        self.assertContains(response, 'autocomplete="new-password"', count=14, html=False)
        self.assertContains(response, 'class="autofill-blocked"', count=15, html=False)
        self.assertContains(response, 'readonly="readonly"', count=15, html=False)
        self.assertContains(response, 'data-form-type="other"', count=15, html=False)
        self.assertContains(response, 'name="new-connection-invite_date" autocomplete="off"', html=False)
        self.assertContains(response, 'data-lpignore="true"', count=1, html=False)
        self.assertContains(response, 'name="new-linkedin_url" autocomplete="off"', html=False)
        self.assertContains(response, 'name="new-wait_0"', html=False)
        self.assertContains(response, 'name="add_professional" value="1"', html=False)
        self.assertContains(response, ">Submit<", html=False)
        self.assertContains(
            response,
            f'data-target="professional-edit-modal-{professional.pk}"',
            html=False,
        )
        self.assertContains(response, f'id="professional-edit-modal-{professional.pk}"')
        self.assertContains(response, f'name="save_professional" value="{professional.pk}"')
        self.assertContains(response, ">Save<", html=False)
        self.assertContains(
            response,
            f'name="delete_professional" value="{professional.pk}"',
            html=False,
        )
        self.assertContains(response, f'href="{professional.linkedin_url}"')
        self.assertContains(
            response,
            f'name="invite_professional" value="{professional.pk}"',
            html=False,
        )
        self.assertContains(
            response,
            f'name="pass_professional" value="{professional.pk}"',
            html=False,
        )
        self.assertContains(response, "15 days")
        self.assertNotContains(response, "15 days, 0:00:00")
        self.assertContains(response, '<tr style="background: #f4cccc;">', html=False)

    def test_professionals_add_button_creates_professional(self):
        response = self.client.post(
            reverse("professionals"),
            data={
                "form-TOTAL_FORMS": "0",
                "form-INITIAL_FORMS": "0",
                "form-MIN_NUM_FORMS": "0",
                "form-MAX_NUM_FORMS": "1000",
                "page": "1",
                "new-name": "Grace Hopper",
                "new-linkedin_url": "https://www.linkedin.com/in/grace-hopper",
                "new-email": "grace@example.com",
                "new-phone": "555-0100",
                "new-wait_0": "0",
                "new-wait_1": "2",
                "new-wait_2": "1",
                "add_professional": "1",
            },
        )

        professional = Professional.objects.get(name="Grace Hopper")
        self.assertRedirects(
            response,
            f"{reverse('professionals')}?page=1&professional_id={professional.pk}",
        )
        self.assertEqual(professional.email, "grace@example.com")
        self.assertEqual(professional.phone, "555-0100")
        self.assertEqual(str(professional.wait), "15 days, 0:00:00")

    def test_professionals_search_displays_selected_professional(self):
        first_professional = Professional.objects.create(name="Ada Lovelace")
        selected_professional = Professional.objects.create(name="Grace Hopper")

        response = self.client.get(
            reverse("professionals"),
            {"professional_id": selected_professional.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_filtered"])
        self.assertEqual(
            [professional.pk for professional in response.context["professionals"]],
            [selected_professional.pk],
        )
        self.assertContains(response, "Search Professional")
        self.assertContains(response, 'id="professional-search"', html=False)
        self.assertContains(response, 'list="professional-search-options"', html=False)
        self.assertContains(
            response,
            f'data-professional-id="{first_professional.pk}"',
            html=False,
        )
        self.assertContains(
            response,
            f'data-professional-id="{selected_professional.pk}"',
            html=False,
        )
        self.assertContains(
            response,
            f'name="professional_id" value="{selected_professional.pk}"',
            html=False,
        )
        self.assertNotContains(response, "Professional 1 of 2")

    def test_professionals_page_displays_current_professionals_companies(self):
        professional = Professional.objects.create(name="Ada Lovelace")
        company = Company.objects.create(
            name="Analytical Engines",
            website="https://analytical-engines.example.com",
            linkedin_url="https://www.linkedin.com/company/analytical-engines",
            email="hello@analytical-engines.example.com",
            phone="555-0100",
        )
        professional.companies.add(company)

        response = self.client.get(reverse("professionals"))

        self.assertContains(response, '<h2 style="margin: 0;">Companies</h2>', html=False)
        self.assertContains(
            response,
            'data-target="companies-section-body">Show</button>',
            html=False,
        )
        self.assertContains(response, 'id="companies-section-body" class="hidden"', html=False)
        self.assertContains(response, '<th>LinkedIn</th>', html=False)
        self.assertContains(
            response,
            f'href="{company.website}"',
            html=False,
        )
        self.assertContains(
            response,
            f"window.open('{company.linkedin_url}', '_blank', 'noopener,noreferrer')",
            html=False,
        )
        self.assertContains(response, company.email)
        self.assertContains(response, company.phone)

    def test_professionals_page_adds_company_to_current_professional(self):
        professional = Professional.objects.create(name="Ada Lovelace")
        company = Company.objects.create(name="Analytical Engines")

        page_response = self.client.get(reverse("professionals"))
        self.assertContains(page_response, 'id="add-company-toggle"', html=False)
        self.assertContains(page_response, 'id="add-company-menu"', html=False)
        self.assertContains(page_response, ">Add Existing<", html=False)
        self.assertContains(
            page_response,
            'data-target="professional-add-company-modal"',
            html=False,
        )
        self.assertContains(
            page_response,
            f'<option value="{company.pk}">{company.name}</option>',
            html=False,
        )

        response = self.client.post(
            reverse("professionals"),
            data={
                "page": "1",
                "company_id": str(company.pk),
                "add_company": str(professional.pk),
            },
        )

        self.assertRedirects(response, f"{reverse('professionals')}?page=1")
        self.assertEqual(list(professional.companies.all()), [company])

    def test_professionals_page_creates_and_links_new_company(self):
        professional = Professional.objects.create(name="Ada Lovelace")

        page_response = self.client.get(reverse("professionals"))
        self.assertNotContains(page_response, 'name="new-company-address"', html=False)
        self.assertContains(
            page_response,
            'name="new-company-email" autocomplete="new-password"',
            html=False,
        )
        self.assertContains(
            page_response,
            'name="new-company-phone" autocomplete="new-password"',
            html=False,
        )
        self.assertContains(
            page_response,
            'name="new-company-description" cols="40" rows="3" style="width: 20rem;"',
            html=False,
        )

        response = self.client.post(
            reverse("professionals"),
            data={
                "page": "1",
                "new-company-name": "Analytical Engines",
                "new-company-website": "https://analytical-engines.example.com",
                "new-company-linkedin_url": "https://www.linkedin.com/company/analytical-engines",
                "new-company-email": "hello@analytical-engines.example.com",
                "new-company-phone": "555-0100",
                "new-company-description": "Computing machinery.",
                "add_new_company": str(professional.pk),
            },
        )

        company = Company.objects.get(name="Analytical Engines")
        self.assertRedirects(response, f"{reverse('professionals')}?page=1")
        self.assertEqual(list(professional.companies.all()), [company])

    def test_professionals_page_displays_current_professionals_referrals(self):
        professional = Professional.objects.create(name="Ada Lovelace")
        referral = Professional.objects.create(
            name="Grace Hopper",
            linkedin_url="https://www.linkedin.com/in/grace-hopper",
            email="grace@example.com",
            phone="555-0101",
        )
        professional.referrals.add(referral)

        response = self.client.get(reverse("professionals"))

        self.assertContains(response, '<h2 style="margin: 0;">Referrals</h2>', html=False)
        self.assertContains(
            response,
            'data-target="referrals-section-body">Show</button>',
            html=False,
        )
        self.assertContains(response, 'id="referrals-section-body" class="hidden"', html=False)
        self.assertContains(
            response,
            f'href="{reverse("professionals")}?professional_id={referral.pk}"',
            html=False,
        )
        self.assertContains(response, "<th>LinkedIn URL</th>", html=False)
        self.assertContains(response, f'href="{referral.linkedin_url}"', html=False)
        self.assertContains(response, referral.email)
        self.assertContains(response, referral.phone)

    def test_professionals_page_adds_existing_referral(self):
        professional = Professional.objects.create(name="Ada Lovelace")
        referral = Professional.objects.create(name="Grace Hopper")

        page_response = self.client.get(reverse("professionals"))
        self.assertContains(page_response, 'id="add-referral-toggle"', html=False)
        self.assertContains(page_response, 'id="add-referral-menu"', html=False)
        self.assertContains(page_response, ">Add Existing<", html=False)
        self.assertContains(
            page_response,
            'data-target="professional-add-referral-modal"',
            html=False,
        )

        response = self.client.post(
            reverse("professionals"),
            data={
                "page": "1",
                "referral_id": str(referral.pk),
                "add_referral": str(professional.pk),
            },
        )

        self.assertRedirects(response, f"{reverse('professionals')}?page=1")
        self.assertEqual(list(professional.referrals.all()), [referral])

    def test_professionals_page_creates_and_links_new_referral(self):
        professional = Professional.objects.create(name="Ada Lovelace")

        response = self.client.post(
            reverse("professionals"),
            data={
                "page": "1",
                "new-referral-name": "Grace Hopper",
                "new-referral-linkedin_url": "https://www.linkedin.com/in/grace-hopper",
                "new-referral-email": "grace@example.com",
                "new-referral-phone": "555-0101",
                "new-referral-wait_0": "0",
                "new-referral-wait_1": "2",
                "new-referral-wait_2": "1",
                "add_new_referral": str(professional.pk),
            },
        )

        referral = Professional.objects.get(name="Grace Hopper")
        self.assertRedirects(response, f"{reverse('professionals')}?page=1")
        self.assertEqual(list(professional.referrals.all()), [referral])
        self.assertEqual(referral.phone, "555-0101")

    def test_professionals_page_displays_current_professionals_referrers(self):
        professional = Professional.objects.create(name="Ada Lovelace")
        referrer = Professional.objects.create(
            name="Grace Hopper",
            linkedin_url="https://www.linkedin.com/in/grace-hopper",
            email="grace@example.com",
            phone="555-0101",
        )
        referrer.referrals.add(professional)

        response = self.client.get(reverse("professionals"))

        self.assertContains(response, '<h2 style="margin: 0;">Referred By</h2>', html=False)
        self.assertContains(
            response,
            'data-target="referred-by-section-body">Show</button>',
            html=False,
        )
        self.assertContains(response, 'id="referred-by-section-body" class="hidden"', html=False)
        self.assertContains(
            response,
            f'href="{reverse("professionals")}?professional_id={referrer.pk}"',
            html=False,
        )
        self.assertContains(response, f'href="{referrer.linkedin_url}"', html=False)
        self.assertContains(response, referrer.email)
        self.assertContains(response, referrer.phone)

    def test_professionals_page_adds_existing_referrer(self):
        professional = Professional.objects.create(name="Ada Lovelace")
        referrer = Professional.objects.create(name="Grace Hopper")

        page_response = self.client.get(reverse("professionals"))
        self.assertContains(page_response, 'id="add-referrer-toggle"', html=False)
        self.assertContains(page_response, 'id="add-referrer-menu"', html=False)
        self.assertContains(
            page_response,
            'data-target="professional-add-referrer-modal"',
            html=False,
        )

        response = self.client.post(
            reverse("professionals"),
            data={
                "page": "1",
                "referrer_id": str(referrer.pk),
                "add_referrer": str(professional.pk),
            },
        )

        self.assertRedirects(response, f"{reverse('professionals')}?page=1")
        self.assertEqual(list(professional.referred_by.all()), [referrer])

    def test_professionals_page_creates_and_links_new_referrer(self):
        professional = Professional.objects.create(name="Ada Lovelace")

        response = self.client.post(
            reverse("professionals"),
            data={
                "page": "1",
                "new-referrer-name": "Grace Hopper",
                "new-referrer-linkedin_url": "https://www.linkedin.com/in/grace-hopper",
                "new-referrer-email": "grace@example.com",
                "new-referrer-phone": "555-0101",
                "new-referrer-wait_0": "0",
                "new-referrer-wait_1": "2",
                "new-referrer-wait_2": "1",
                "add_new_referrer": str(professional.pk),
            },
        )

        referrer = Professional.objects.get(name="Grace Hopper")
        self.assertRedirects(response, f"{reverse('professionals')}?page=1")
        self.assertEqual(list(professional.referred_by.all()), [referrer])

    def test_professionals_page_shows_current_professionals_invitations(self):
        professional = Professional.objects.create(name="Ada Lovelace")
        other_professional = Professional.objects.create(name="Grace Hopper")
        older_invitation = ProfessionalConnect.objects.create(
            professional=professional,
            invite_date=date(2026, 8, 1),
            notes="Older invitation",
        )
        newer_invitation = ProfessionalConnect.objects.create(
            professional=professional,
            invite_date=date(2026, 8, 2),
            notes="Newer invitation",
        )
        ProfessionalConnect.objects.create(
            professional=professional,
            meeting_at=timezone.make_aware(datetime(2026, 8, 3, 9, 0)),
            notes="No invitation",
        )
        ProfessionalConnect.objects.create(
            professional=other_professional,
            invite_date=date(2026, 8, 4),
            notes="Other professional invitation",
        )

        response = self.client.get(reverse("professionals"))

        self.assertContains(response, '<h2 style="margin: 0;">Connections</h2>', html=False)
        self.assertContains(response, "<th>Status</th>", html=False)
        self.assertContains(response, "<th>Edit</th>", html=False)
        self.assertContains(
            response,
            f'data-target="invitation-edit-modal-{newer_invitation.pk}"',
            html=False,
        )
        self.assertContains(
            response,
            f'name="invitation-{newer_invitation.pk}-invite_date" value="2026-08-02" autocomplete="off"',
            html=False,
        )
        self.assertContains(response, 'data-lpignore="true"', count=3, html=False)
        self.assertContains(response, "Waiting For Response")
        self.assertContains(response, "Invited Again")
        self.assertContains(response, "Newer invi...")
        self.assertContains(response, "Older invi...")
        self.assertContains(
            response,
            f'name="delete_invitation" value="{newer_invitation.pk}"',
            html=False,
        )
        self.assertNotContains(response, "Sync to Google Calendar")
        self.assertContains(response, "No invitation")
        self.assertNotContains(response, "Other professional invitation")
        self.assertLess(
            response.content.find(b"Newer invi..."),
            response.content.find(b"Older invi..."),
        )
        self.assertEqual(
            list(response.context["invitations"]),
            [newer_invitation, older_invitation],
        )

    @patch("app.views.sync_professional_connect")
    def test_professionals_page_edits_current_professionals_invitation(self, mock_sync):
        professional = Professional.objects.create(name="Ada Lovelace")
        invitation = ProfessionalConnect.objects.create(
            professional=professional,
            invite_date=date(2026, 8, 1),
            notes="Initial notes",
        )
        mock_sync.return_value = {
            "meeting": {"status": "updated", "message": "Meeting updated."},
        }

        response = self.client.post(
            reverse("professionals"),
            data={
                "page": "1",
                f"invitation-{invitation.pk}-invite_date": "2026-08-02",
                f"invitation-{invitation.pk}-meeting_at": "2026-08-03T09:30",
                f"invitation-{invitation.pk}-rating": "5",
                f"invitation-{invitation.pk}-notes": "Updated notes",
                "save_invitation": str(invitation.pk),
            },
            follow=True,
        )

        self.assertRedirects(response, f"{reverse('professionals')}?page=1")
        self.assertContains(response, "Connection saved and synchronized to Google Calendar.")
        invitation.refresh_from_db()
        self.assertEqual(invitation.invite_date, date(2026, 8, 2))
        self.assertEqual(invitation.rating, 5)
        self.assertEqual(invitation.notes, "Updated notes")
        mock_sync.assert_called_once_with(invitation)

    @patch("app.views.sync_professional_connect")
    def test_professionals_page_keeps_connection_save_when_google_sync_fails(
        self, mock_sync
    ):
        professional = Professional.objects.create(name="Ada Lovelace")
        invitation = ProfessionalConnect.objects.create(
            professional=professional,
            invite_date=date(2026, 8, 1),
            notes="Initial notes",
        )
        mock_sync.return_value = {
            "meeting": {"status": "error", "message": "Google API unavailable."},
        }

        response = self.client.post(
            reverse("professionals"),
            data={
                "page": "1",
                f"invitation-{invitation.pk}-invite_date": "2026-08-02",
                f"invitation-{invitation.pk}-meeting_at": "2026-08-03T09:30",
                f"invitation-{invitation.pk}-rating": "4",
                f"invitation-{invitation.pk}-notes": "Saved despite sync failure",
                "save_invitation": str(invitation.pk),
            },
            follow=True,
        )

        self.assertRedirects(response, f"{reverse('professionals')}?page=1")
        self.assertContains(
            response, "Connection saved, but Google Calendar sync failed."
        )
        invitation.refresh_from_db()
        self.assertEqual(invitation.rating, 4)
        self.assertEqual(invitation.notes, "Saved despite sync failure")

    def test_professionals_page_builds_notes_from_connections_newest_first(self):
        professional = Professional.objects.create(name="Ada Lovelace")
        ProfessionalConnect.objects.create(
            professional=professional,
            invite_date=date(2026, 9, 1),
            notes="Old invite note",
        )
        ProfessionalConnect.objects.create(
            professional=professional,
            meeting_at=datetime(2026, 9, 3, 14, 30, tzinfo=UTC),
            notes="Meeting note",
        )
        ProfessionalConnect.objects.create(
            professional=professional,
            invite_date=date(2026, 9, 5),
            notes="Newest invite note",
        )
        ProfessionalConnect.objects.create(
            professional=professional,
            invite_date=date(2026, 9, 6),
            notes="   ",
        )

        response = self.client.get(reverse("professionals"))

        self.assertContains(response, '<h2 style="margin: 0;">Notes</h2>', html=False)
        self.assertContains(
            response,
            'data-target="notes-section-body">Show</button>',
            html=False,
        )
        self.assertContains(response, 'id="notes-section-body" class="hidden"', html=False)
        self.assertContains(response, "2026-09-05")
        self.assertContains(response, "2026-09-03 14:30")
        self.assertContains(response, "2026-09-01")
        self.assertEqual(
            [note["notes"] for note in response.context["connection_notes"]],
            ["Newest invite note", "Meeting note", "Old invite note"],
        )

    def test_professionals_page_groups_directions_by_resolution_and_meeting_date(self):
        professional = Professional.objects.create(name="Ada Lovelace")
        other_professional = Professional.objects.create(name="Grace Hopper")
        recent_connection = ProfessionalConnect.objects.create(
            professional=professional,
            meeting_at=datetime(2026, 9, 5, 14, 30, tzinfo=UTC),
        )
        older_connection = ProfessionalConnect.objects.create(
            professional=professional,
            meeting_at=datetime(2026, 9, 3, 9, 0, tzinfo=UTC),
        )
        undated_connection = ProfessionalConnect.objects.create(professional=professional)
        other_connection = ProfessionalConnect.objects.create(
            professional=other_professional,
            meeting_at=datetime(2026, 9, 6, 9, 0, tzinfo=UTC),
        )
        recent_unresolved = Direction.objects.create(
            connect=recent_connection,
            description="Recent unresolved direction",
        )
        older_unresolved = Direction.objects.create(
            connect=older_connection,
            description="Older unresolved direction",
        )
        undated_unresolved = Direction.objects.create(
            connect=undated_connection,
            description="Undated unresolved direction",
        )
        resolved = Direction.objects.create(
            connect=older_connection,
            description="Resolved direction",
            resolved=True,
        )
        Direction.objects.create(
            connect=other_connection,
            description="Other professional direction",
        )

        response = self.client.get(reverse("professionals"))

        self.assertContains(response, '<h2 style="margin: 0;">Directions</h2>', html=False)
        self.assertContains(
            response,
            'data-target="directions-section-body">Show</button>',
            html=False,
        )
        self.assertContains(response, 'id="directions-section-body" class="hidden', html=False)
        self.assertContains(response, "<h3>Unresolved</h3>", html=False)
        self.assertContains(response, "<h3>Resolved</h3>", html=False)
        self.assertContains(response, "No meeting date")
        self.assertNotContains(response, "Other professional direction")
        self.assertEqual(
            response.context["unresolved_directions"],
            [recent_unresolved, older_unresolved, undated_unresolved],
        )
        self.assertEqual(response.context["resolved_directions"], [resolved])

        update_response = self.client.post(
            reverse("professionals"),
            data={
                "page": "1",
                "direction_resolved": "on",
                "update_direction": str(recent_unresolved.pk),
            },
        )
        self.assertRedirects(update_response, f"{reverse('professionals')}?page=1")
        recent_unresolved.refresh_from_db()
        self.assertTrue(recent_unresolved.resolved)

    @patch("app.views.delete_meeting_event")
    def test_professionals_page_deletes_current_professionals_connection(
        self, mock_delete_meeting_event
    ):
        professional = Professional.objects.create(name="Ada Lovelace")
        invitation = ProfessionalConnect.objects.create(
            professional=professional,
            invite_date=date(2026, 8, 1),
            google_meeting_event_id="google-event-id",
        )

        response = self.client.post(
            reverse("professionals"),
            data={
                "page": "1",
                "delete_invitation": str(invitation.pk),
            },
        )

        self.assertRedirects(response, f"{reverse('professionals')}?page=1")
        self.assertFalse(ProfessionalConnect.objects.filter(pk=invitation.pk).exists())
        mock_delete_meeting_event.assert_called_once()

    @patch("app.views.sync_professional_connect")
    def test_professionals_page_adds_connection_for_current_professional(self, mock_sync):
        professional = Professional.objects.create(name="Ada Lovelace")
        mock_sync.return_value = {
            "meeting": {"status": "created", "message": "Meeting created."}
        }

        page_response = self.client.get(reverse("professionals"))
        self.assertContains(
            page_response,
            'data-target="connections-section-body">Show</button>',
            html=False,
        )
        self.assertContains(page_response, 'id="connections-section-body" class="hidden"', html=False)
        self.assertContains(page_response, 'data-target="connection-add-modal"', html=False)

        response = self.client.post(
            reverse("professionals"),
            data={
                "page": "1",
                "new-connection-invite_date": "2026-09-01",
                "new-connection-meeting_at": "2026-09-02T09:30",
                "new-connection-rating": "5",
                "new-connection-notes": "New connection",
                "add_connection": str(professional.pk),
            },
        )

        connection = ProfessionalConnect.objects.get(professional=professional)
        self.assertEqual(connection.description, "Ian x Ada Lovelace")
        self.assertRedirects(response, f"{reverse('professionals')}?page=1")
        self.assertEqual(connection.invite_date, date(2026, 9, 1))
        self.assertEqual(connection.rating, 5)
        self.assertEqual(connection.notes, "New connection")
        mock_sync.assert_called_once_with(connection)

    @patch("app.views.sync_professional_connect")
    def test_professionals_connection_time_matches_connections_calendar(self, mock_sync):
        professional = Professional.objects.create(name="Ada Lovelace")
        mock_sync.return_value = {
            "meeting": {"status": "created", "message": "Meeting created."}
        }

        self.client.post(
            reverse("professionals"),
            data={
                "page": "1",
                "new-connection-invite_date": "2026-09-10",
                "new-connection-meeting_at": "2026-09-10T22:25",
                "add_connection": str(professional.pk),
            },
        )

        connection = ProfessionalConnect.objects.get(professional=professional)
        self.assertEqual(
            timezone.localtime(connection.meeting_at, ZoneInfo("America/Denver")),
            datetime(2026, 9, 10, 22, 25, tzinfo=ZoneInfo("America/Denver")),
        )
        calendar_event = self.client.get(reverse("connection_events")).json()[0]
        self.assertEqual(calendar_event["start"], "2026-09-10T22:25:00")

    def test_professionals_connections_table_uses_am_pm_for_meeting_time(self):
        professional = Professional.objects.create(name="Ada Lovelace")
        ProfessionalConnect.objects.create(
            professional=professional,
            invite_date=date(2026, 9, 10),
            meeting_at=datetime(2026, 9, 10, 14, 25, tzinfo=UTC),
        )

        response = self.client.get(reverse("professionals"))

        self.assertContains(response, "2026-09-10 8:25 AM")

    def test_professionals_edit_existing_cards(self):
        professional = Professional.objects.create(
            name="Ada Lovelace",
            linkedin_url="https://www.linkedin.com/in/ada-lovelace",
            email="ada@example.com",
        )

        edit_response = self.client.post(
            reverse("professionals"),
            data={
                "page": "1",
                f"edit-{professional.pk}-name": "Ada Lovelace Updated",
                f"edit-{professional.pk}-linkedin_url": "https://www.linkedin.com/in/ada-updated",
                f"edit-{professional.pk}-email": "updated@example.com",
                f"edit-{professional.pk}-phone": "555-0100",
                f"edit-{professional.pk}-wait_0": "1",
                f"edit-{professional.pk}-wait_1": "0",
                f"edit-{professional.pk}-wait_2": "2",
                "save_professional": str(professional.pk),
            },
        )

        self.assertRedirects(edit_response, f"{reverse('professionals')}?page=1")
        professional.refresh_from_db()
        self.assertEqual(professional.name, "Ada Lovelace Updated")
        self.assertEqual(professional.email, "updated@example.com")
        self.assertEqual(professional.phone, "555-0100")
        self.assertEqual(str(professional.wait), "32 days, 0:00:00")

    def test_professionals_page_uses_latest_connection_dates(self):
        professional = Professional.objects.create(
            name="Ada Lovelace",
            wait=timedelta(days=15),
        )
        first_connected_at = timezone.make_aware(datetime(2026, 8, 1, 9, 30))
        last_connected_at = timezone.make_aware(datetime(2026, 8, 2, 10, 45))
        ProfessionalConnect.objects.create(
            professional=professional,
            invite_date=date(2026, 7, 1),
            meeting_at=first_connected_at,
        )
        ProfessionalConnect.objects.create(
            professional=professional,
            invite_date=date(2026, 7, 15),
            meeting_at=last_connected_at,
        )

        response = self.client.get(reverse("professionals"))

        displayed_professional = list(response.context["professionals"])[0]
        self.assertEqual(displayed_professional.last_invited, date(2026, 7, 15))
        self.assertEqual(displayed_professional.last_connected, last_connected_at)
        self.assertEqual(displayed_professional.invite_due, date(2026, 8, 15))
        self.assertEqual(
            displayed_professional.connect_due,
            date(2026, 8, 17),
        )

    def test_professional_connect_due_uses_calendar_months(self):
        professional = Professional.objects.create(
            name="Jacob Pyrett",
            wait=timedelta(days=90),
        )
        ProfessionalConnect.objects.create(
            professional=professional,
            meeting_at=datetime(2026, 6, 13, 0, 0, tzinfo=ZoneInfo("America/Denver")),
        )

        self.assertEqual(professional.connect_due, date(2026, 9, 13))

    def test_professionals_page_calculates_average_rating(self):
        professional = Professional.objects.create(name="Ada Lovelace")
        ProfessionalConnect.objects.create(professional=professional, rating=4)
        ProfessionalConnect.objects.create(professional=professional, rating=5)
        ProfessionalConnect.objects.create(professional=professional)

        response = self.client.get(reverse("professionals"))

        displayed_professional = list(response.context["professionals"])[0]
        self.assertEqual(displayed_professional.average_rating, 4.5)
        self.assertEqual(displayed_professional.average_rating_stars, "★★★★★")
        self.assertContains(response, "★★★★★")

    def test_professionals_page_calculates_invite_success(self):
        professional = Professional.objects.create(name="Ada Lovelace")
        ProfessionalConnect.objects.create(
            professional=professional,
            meeting_at=timezone.make_aware(datetime(2026, 8, 1, 9, 0)),
        )
        ProfessionalConnect.objects.create(professional=professional)
        ProfessionalConnect.objects.create(professional=professional)

        response = self.client.get(reverse("professionals"))

        displayed_professional = list(response.context["professionals"])[0]
        self.assertAlmostEqual(displayed_professional.invite_success, 100 / 3)
        self.assertContains(response, "33.3%")

    def test_professionals_page_calculates_invite_without_database_field(self):
        never_invited = Professional.objects.create(name="Never Invited")
        overdue_invite = Professional.objects.create(name="Overdue Invite")
        current_connect = Professional.objects.create(
            name="Current Connect",
            wait=timedelta(days=1),
        )
        future_connect = Professional.objects.create(
            name="Future Connect",
            wait=timedelta(days=30),
        )
        current_date = timezone.localdate()
        current_datetime = timezone.now()
        attended_at = current_datetime - timedelta(days=2)

        ProfessionalConnect.objects.create(
            professional=overdue_invite,
            invite_date=current_date - timedelta(days=35),
        )
        ProfessionalConnect.objects.create(
            professional=current_connect,
            invite_date=current_date - timedelta(days=3),
            meeting_at=attended_at,
        )
        ProfessionalConnect.objects.create(
            professional=future_connect,
            invite_date=current_date - timedelta(days=3),
            meeting_at=current_datetime,
        )

        displayed_professionals = {}
        for page_number in range(1, 5):
            response = self.client.get(reverse("professionals"), {"page": page_number})
            displayed_professionals.update(
                {
                    professional.name: professional
                    for professional in response.context["professionals"]
                }
            )
        self.assertTrue(displayed_professionals[never_invited.name].invite)
        self.assertTrue(displayed_professionals[overdue_invite.name].invite)
        self.assertTrue(displayed_professionals[current_connect.name].invite)
        self.assertFalse(displayed_professionals[future_connect.name].invite)
        self.assertTrue(never_invited.invite)
        self.assertNotIn(
            "invite",
            [field.name for field in Professional._meta.get_fields()],
        )

    def test_professionals_page_sorts_by_invite_and_due_dates(self):
        current_date = timezone.localdate()
        current_datetime = timezone.now()
        first = Professional.objects.create(
            name="Alpha",
            wait=timedelta(days=10),
        )
        second = Professional.objects.create(
            name="Beta",
            wait=timedelta(days=10),
        )
        third = Professional.objects.create(
            name="Charlie",
            wait=timedelta(days=11),
        )
        fourth = Professional.objects.create(
            name="Delta",
            wait=timedelta(days=11),
        )
        last = Professional.objects.create(
            name="Future Connect",
            wait=timedelta(days=30),
        )

        ProfessionalConnect.objects.create(
            professional=first,
            invite_date=current_date - timedelta(days=40),
            meeting_at=current_datetime - timedelta(days=11),
        )
        ProfessionalConnect.objects.create(
            professional=second,
            invite_date=current_date - timedelta(days=35),
            meeting_at=current_datetime - timedelta(days=11),
        )
        for professional in (third, fourth):
            ProfessionalConnect.objects.create(
                professional=professional,
                invite_date=current_date - timedelta(days=35),
                meeting_at=current_datetime - timedelta(days=12),
            )
        ProfessionalConnect.objects.create(
            professional=last,
            invite_date=current_date - timedelta(days=3),
            meeting_at=current_datetime,
        )

        response = self.client.get(reverse("professionals"))

        self.assertEqual(
            [professional.name for professional in response.context["professionals"]],
            ["Alpha"],
        )

        second_page_response = self.client.get(reverse("professionals"), {"page": 2})

        self.assertEqual(
            [professional.name for professional in second_page_response.context["professionals"]],
            ["Charlie"],
        )
        self.assertContains(second_page_response, "Professional 2 of 5")
        self.assertContains(
            second_page_response,
            'display: flex; justify-content: center; align-items: center; gap: 1rem;',
            html=False,
        )
        self.assertContains(
            second_page_response,
            'aria-label="Previous professional"',
            html=False,
        )
        self.assertContains(
            second_page_response,
            'aria-label="Next professional"',
            html=False,
        )
        self.assertContains(second_page_response, "&larr;", html=False)
        self.assertContains(second_page_response, "&rarr;", html=False)

    def test_professionals_invite_creates_connect_and_shows_message(self):
        professional = Professional.objects.create(name="Ada Lovelace")

        invite_response = self.client.post(
            reverse("professionals"),
            data={
                "page": "1",
                "invite_professional": str(professional.pk),
            },
        )

        self.assertRedirects(
            invite_response,
            f"{reverse('professionals')}?page=1&invited_professional={professional.pk}",
        )
        connect = ProfessionalConnect.objects.get(professional=professional)
        self.assertEqual(connect.description, "Ian x Ada Lovelace")
        self.assertEqual(connect.invite_date, timezone.localdate())

        response = self.client.get(
            reverse("professionals"),
            {"invited_professional": professional.pk},
        )

        self.assertContains(response, 'id="professional-invite-modal"', html=False)
        self.assertContains(
            response,
            'data-copy-source="professional-invite-message"',
            html=False,
        )
        self.assertContains(response, 'id="professional-invite-message"', html=False)
        self.assertContains(response, "Hello Ada Lovelace.")
        self.assertContains(
            response,
            "I have a Master's in Data Science, and I am currently looking for data engineering and software engineering roles focused in Python and SQL.",
        )

    @patch("app.views.sync_professional_connect")
    def test_professionals_connection_form_prevents_overlapping_meeting(
        self, mock_sync
    ):
        mountain_timezone = ZoneInfo("America/Denver")
        professional = Professional.objects.create(name="Ada Lovelace")
        ProfessionalConnect.objects.create(
            professional=professional,
            description="Existing connection",
            meeting_at=datetime(2026, 9, 15, 9, 0, tzinfo=mountain_timezone),
            meeting_end=datetime(2026, 9, 15, 10, 0, tzinfo=mountain_timezone),
        )

        response = self.client.post(
            reverse("professionals"),
            data={
                "page": "1",
                "add_connection": str(professional.pk),
                "new-connection-invite_date": "2026-09-15",
                "new-connection-meeting_at": "2026-09-15T09:30",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This meeting conflicts with")
        self.assertEqual(ProfessionalConnect.objects.count(), 1)
        mock_sync.assert_not_called()

    def test_professionals_pass_deletes_professional_and_logs_connection(self):
        professional = Professional.objects.create(name="Ada Lovelace")

        response = self.client.post(
            reverse("professionals"),
            data={
                "page": "1",
                "pass_professional": str(professional.pk),
            },
        )

        self.assertRedirects(response, f"{reverse('professionals')}?page=1")
        self.assertFalse(Professional.objects.filter(pk=professional.pk).exists())
        passed_connection = ProfessionalConnect.objects.get(
            description="Passed on Ada Lovelace"
        )
        self.assertEqual(passed_connection.invite_date, timezone.localdate())
        self.assertIsNone(passed_connection.professional)

    def test_professionals_delete_existing_cards_from_edit_modal(self):
        professional = Professional.objects.create(name="Ada Lovelace")

        delete_response = self.client.post(
            reverse("professionals"),
            data={
                "page": "1",
                "delete_professional": str(professional.pk),
            },
        )

        self.assertRedirects(delete_response, f"{reverse('professionals')}?page=1")
        self.assertFalse(Professional.objects.filter(pk=professional.pk).exists())


class CompanyPageTests(TestCase):
    def test_companies_page_paginates_ten_companies_per_page(self):
        companies = [
            Company(name=f"Company {index:02d}") for index in range(1, 12)
        ]
        Company.objects.bulk_create(companies)

        first_page = self.client.get(reverse("companies"))
        second_page = self.client.get(reverse("companies"), {"page": 2})

        self.assertContains(first_page, "Company 10")
        self.assertNotContains(first_page, "Company 11")
        self.assertContains(first_page, "Page 1 of 2")
        self.assertContains(second_page, "Company 11")
        self.assertNotContains(second_page, "Company 01")
        self.assertContains(second_page, "Page 2 of 2")

    def test_companies_page_displays_companies_and_add_modal(self):
        company = Company.objects.create(
            name="Analytical Engines",
            website="https://analytical-engines.example.com",
            linkedin_url="https://www.linkedin.com/company/analytical-engines",
            email="contact@example.com",
            phone="555-0100",
        )

        response = self.client.get(reverse("companies"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Companies")
        self.assertContains(response, 'id="open-add-company-modal"', html=False)
        self.assertContains(response, 'id="add-company-modal"', html=False)
        self.assertContains(response, company.website)
        self.assertContains(response, company.linkedin_url)
        self.assertContains(response, company.email)
        self.assertContains(response, company.phone)
        self.assertContains(response, "Job Search")
        self.assertContains(response, "Search Terms")
        self.assertContains(response, "Yes")

    def test_companies_page_creates_company_from_modal_form(self):
        response = self.client.post(
            reverse("companies"),
            {
                "new-company-name": "New Company",
                "new-company-website": "https://new-company.example.com",
                "new-company-linkedin_url": "https://www.linkedin.com/company/new-company",
                "new-company-email": "contact@new-company.example.com",
                "new-company-phone": "555-0101",
                "new-company-description": "A new company.",
                "add_company": "1",
            },
        )

        self.assertRedirects(response, reverse("companies"))
        self.assertTrue(Company.objects.filter(name="New Company").exists())

    def test_companies_page_edits_and_deletes_company_from_edit_modal(self):
        company = Company.objects.create(
            name="Analytical Engines",
            website="https://analytical-engines.example.com",
        )

        page_response = self.client.get(reverse("companies"))
        self.assertContains(page_response, "<th>Edit</th>", html=False)
        self.assertContains(
            page_response,
            f'data-target="edit-company-modal-{company.pk}"',
            html=False,
        )
        self.assertContains(page_response, "Edit Company")
        self.assertContains(
            page_response,
            f'name="edit-company-{company.pk}-website"',
            html=False,
        )
        self.assertContains(
            page_response,
            'autocomplete="new-password" class="autofill-blocked" data-form-type="other"',
            html=False,
        )

        save_response = self.client.post(
            reverse("companies"),
            {
                f"edit-company-{company.pk}-name": "Analytical Engines Updated",
                f"edit-company-{company.pk}-website": "https://updated.example.com",
                f"edit-company-{company.pk}-linkedin_url": "",
                f"edit-company-{company.pk}-email": "",
                f"edit-company-{company.pk}-phone": "",
                f"edit-company-{company.pk}-description": "",
                f"edit-company-{company.pk}-job_search_enabled": "",
                f"edit-company-{company.pk}-supports_job_search_terms": "",
                "save_company": company.pk,
            },
        )
        self.assertRedirects(save_response, reverse("companies"))
        company.refresh_from_db()
        self.assertEqual(company.name, "Analytical Engines Updated")
        self.assertFalse(company.job_search_enabled)
        self.assertFalse(company.supports_job_search_terms)

        delete_response = self.client.post(
            reverse("companies"),
            {"delete_company": company.pk},
        )
        self.assertRedirects(delete_response, reverse("companies"))
        self.assertFalse(Company.objects.filter(pk=company.pk).exists())

    def test_companies_page_edit_returns_to_current_page(self):
        Company.objects.bulk_create(
            [Company(name=f"Company {index:02d}") for index in range(1, 12)]
        )
        company = Company.objects.get(name="Company 11")

        response = self.client.post(
            f"{reverse('companies')}?page=2",
            {
                "page": "2",
                f"edit-company-{company.pk}-name": "Company Updated",
                f"edit-company-{company.pk}-website": "",
                f"edit-company-{company.pk}-linkedin_url": "",
                f"edit-company-{company.pk}-email": "",
                f"edit-company-{company.pk}-phone": "",
                f"edit-company-{company.pk}-description": "",
                "save_company": company.pk,
            },
        )

        self.assertRedirects(response, f"{reverse('companies')}?page=2")
        company.refresh_from_db()
        self.assertEqual(company.name, "Company Updated")


class SearchTermsPageTests(TestCase):
    def test_search_terms_page_displays_terms_alphabetically(self):
        SearchTerm.objects.create(term="Python", active=False)
        SearchTerm.objects.create(term="Data Engineer")

        response = self.client.get(reverse("search_terms"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Search Terms")
        self.assertContains(response, 'id="open-add-search-term-modal"', html=False)
        self.assertLess(
            response.content.index(b"Data Engineer"),
            response.content.index(b"Python"),
        )
        self.assertContains(response, "Yes")
        self.assertContains(response, "No")

    def test_search_terms_page_creates_and_edits_search_term(self):
        create_response = self.client.post(
            reverse("search_terms"),
            {
                "new-search-term-term": "Python",
                "new-search-term-active": "on",
                "add_search_term": "1",
            },
        )

        self.assertRedirects(create_response, reverse("search_terms"))
        search_term = SearchTerm.objects.get(term="Python")

        edit_response = self.client.post(
            reverse("search_terms"),
            {
                f"edit-search-term-{search_term.pk}-term": "Django",
                "save_search_term": search_term.pk,
            },
        )

        self.assertRedirects(edit_response, reverse("search_terms"))
        search_term.refresh_from_db()
        self.assertEqual(search_term.term, "Django")
        self.assertFalse(search_term.active)

    def test_deleting_search_term_preserves_paths_and_observations(self):
        search_term = SearchTerm.objects.create(term="Python")
        platform = Platform.objects.create(name="Example Platform")
        search_path = SearchPath.objects.create(
            platform=platform,
            search_term=search_term,
        )
        observation = SearchObservation.objects.create(search_path=search_path)

        page_response = self.client.get(reverse("search_terms"))
        self.assertContains(page_response, "Search paths and historical observations will be kept.")

        delete_response = self.client.post(
            reverse("search_terms"),
            {"delete_search_term": search_term.pk},
        )

        self.assertRedirects(delete_response, reverse("search_terms"))
        self.assertFalse(SearchTerm.objects.filter(pk=search_term.pk).exists())
        search_path.refresh_from_db()
        self.assertIsNone(search_path.search_term)
        self.assertTrue(SearchObservation.objects.filter(pk=observation.pk).exists())


class CreateSearchPathsCommandTests(TestCase):
    def test_command_creates_only_missing_valid_search_paths_idempotently(self):
        active_first = SearchTerm.objects.create(term="Django")
        active_second = SearchTerm.objects.create(term="Python")
        inactive = SearchTerm.objects.create(term="Inactive", active=False)
        disabled_company = Company.objects.create(
            name="Disabled Company",
            job_search_enabled=False,
        )
        company_without_terms = Company.objects.create(
            name="Company Without Terms",
            supports_job_search_terms=False,
        )
        company_with_terms = Company.objects.create(name="Company With Terms")
        disabled_platform = Platform.objects.create(
            name="Disabled Platform",
            job_search_enabled=False,
        )
        platform = Platform.objects.create(name="Platform")
        SearchPath.objects.create(company=company_without_terms)

        output = StringIO()
        call_command("create_search_paths", stdout=output)

        self.assertIn("SearchPaths created: 5", output.getvalue())
        self.assertIn("SearchPaths already existed: 1", output.getvalue())
        self.assertFalse(SearchPath.objects.filter(company=disabled_company).exists())
        self.assertFalse(SearchPath.objects.filter(platform=disabled_platform).exists())
        self.assertFalse(SearchPath.objects.filter(search_term=inactive).exists())
        self.assertEqual(
            SearchPath.objects.filter(company=company_without_terms).count(),
            1,
        )
        self.assertEqual(
            SearchPath.objects.filter(company=company_with_terms).count(),
            3,
        )
        self.assertEqual(SearchPath.objects.filter(platform=platform).count(), 2)
        self.assertFalse(
            SearchPath.objects.filter(platform=platform, search_term__isnull=True).exists()
        )
        self.assertTrue(
            SearchPath.objects.filter(
                company=company_with_terms,
                search_term=active_first,
            ).exists()
        )
        self.assertTrue(
            SearchPath.objects.filter(
                company=company_with_terms,
                search_term=active_second,
            ).exists()
        )

        repeated_output = StringIO()
        call_command("create_search_paths", stdout=repeated_output)

        self.assertIn("SearchPaths created: 0", repeated_output.getvalue())
        self.assertIn("SearchPaths already existed: 6", repeated_output.getvalue())


class JobSearchPageTests(TestCase):
    def test_job_search_filters_hidden_paths_and_sorts_visible_paths_by_alpha(self):
        low_platform = Platform.objects.create(name="Low Alpha Platform")
        high_platform = Platform.objects.create(name="High Alpha Platform")
        company = Company.objects.create(name="Most Recently Searched Company")
        low_path = SearchPath.objects.create(
            platform=low_platform,
            url="https://low-alpha.example.com",
        )
        high_path = SearchPath.objects.create(platform=high_platform)
        hidden_path = SearchPath.objects.create(company=company)
        success_posting = JobPosting.objects.create(
            title="Success",
            company_name="Example",
            apply_to=True,
        )
        unsuccessful_posting = JobPosting.objects.create(
            title="Unsuccessful",
            company_name="Example",
            apply_to=False,
        )
        SearchObservation.objects.create(
            search_path=low_path,
            job_posting=success_posting,
            complete=True,
        )
        SearchObservation.objects.create(
            search_path=high_path,
            job_posting=unsuccessful_posting,
            complete=True,
        )
        latest_observation = SearchObservation.objects.create(
            search_path=hidden_path,
            complete=True,
        )
        SearchObservation.objects.filter(pk=latest_observation.pk).update(
            created=timezone.now() + timedelta(days=1)
        )

        first_page = self.client.get(reverse("job_search"))
        second_page = self.client.get(reverse("job_search"), {"page": 2})

        self.assertEqual(first_page.status_code, 200)
        self.assertContains(first_page, "Job Search")
        self.assertContains(first_page, "Success Count")
        self.assertContains(first_page, "Observation Count")
        self.assertContains(first_page, "Success Probability")
        self.assertContains(first_page, str(low_path))
        self.assertContains(first_page, f'href="{low_path.url}"', html=False)
        self.assertContains(first_page, "Job Search 1 of 2")
        self.assertNotContains(first_page, str(hidden_path))
        self.assertContains(second_page, str(high_path))
        self.assertContains(second_page, "Job Search 2 of 2")

    def test_job_search_saves_the_current_search_path_formset(self):
        platform = Platform.objects.create(name="Example Platform")
        search_path = SearchPath.objects.create(platform=platform)

        response = self.client.post(
            reverse("job_search"),
            {
                "form-TOTAL_FORMS": "1",
                "form-INITIAL_FORMS": "1",
                "form-MIN_NUM_FORMS": "0",
                "form-MAX_NUM_FORMS": "1000",
                "form-0-id": search_path.pk,
                "form-0-url": "https://jobs.example.com",
                "form-0-active": "on",
                "page": "1",
                "save_search_path": "1",
            },
        )

        self.assertRedirects(response, f"{reverse('job_search')}?page=1")
        search_path.refresh_from_db()
        self.assertEqual(search_path.url, "https://jobs.example.com")


class RecruiterPageTests(TestCase):
    def test_recruiters_page_adds_recruiter_and_selects_it(self):
        response = self.client.post(
            reverse("recruiters"),
            {
                "page": "1",
                "new-name": "Ada Recruiter",
                "new-linkedin_url": "https://www.linkedin.com/in/ada-recruiter",
                "new-email": "ada@example.com",
                "new-phone": "555-0100",
                "new-wait_0": "0",
                "new-wait_1": "1",
                "new-wait_2": "0",
                "add_recruiter": "1",
            },
        )

        recruiter = Recruiter.objects.get(name="Ada Recruiter")
        self.assertRedirects(
            response,
            f"{reverse('recruiters')}?page=1&recruiter_id={recruiter.pk}",
        )

    @patch("app.views.sync_professional_connect")
    def test_recruiter_connection_uses_shared_connect_without_professional(
        self, mock_sync
    ):
        recruiter = Recruiter.objects.create(name="Ada Recruiter")
        professional = Professional.objects.create(name="Ada Professional")
        mock_sync.return_value = {"meeting": {"status": "created"}}

        response = self.client.post(
            reverse("recruiters"),
            {
                "page": "1",
                "recruiter_id": recruiter.pk,
                "new-connection-invite_date": "2026-09-12",
                "new-connection-meeting_at": "2026-09-13T10:00",
                "add_connection": recruiter.pk,
            },
        )

        connection = Connect.objects.get(recruiter=recruiter)
        self.assertRedirects(response, f"{reverse('recruiters')}?page=1&recruiter_id={recruiter.pk}")
        self.assertIsNone(connection.professional)
        self.assertNotEqual(connection.professional_id, professional.pk)
        self.assertEqual(list(recruiter.connects.all()), [connection])
        mock_sync.assert_called_once_with(connection)

    @patch("app.views.sync_professional_connect")
    def test_recruiter_connection_conflicts_with_professional_meeting(self, mock_sync):
        mountain_timezone = ZoneInfo("America/Denver")
        professional = Professional.objects.create(name="Ada Professional")
        recruiter = Recruiter.objects.create(name="Ada Recruiter")
        Connect.objects.create(
            professional=professional,
            meeting_at=datetime(2026, 9, 15, 9, 0, tzinfo=mountain_timezone),
            meeting_end=datetime(2026, 9, 15, 10, 0, tzinfo=mountain_timezone),
        )

        response = self.client.post(
            reverse("recruiters"),
            {
                "page": "1",
                "recruiter_id": recruiter.pk,
                "new-connection-invite_date": "2026-09-15",
                "new-connection-meeting_at": "2026-09-15T09:30",
                "add_connection": recruiter.pk,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This meeting conflicts with")
        self.assertFalse(Connect.objects.filter(recruiter=recruiter).exists())
        mock_sync.assert_not_called()


class ConnectionsCalendarTests(TestCase):
    def setUp(self):
        self.professional = Professional.objects.create(name="Calendar Professional")

    def test_connections_page_includes_editable_fullcalendar(self):
        response = self.client.get(reverse("connections"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="connections-calendar"')
        self.assertContains(response, 'data-date-mode="meeting"')
        self.assertContains(response, 'data-date-mode="invite-professionals"')
        self.assertContains(response, 'data-date-mode="invite-recruiters"')
        self.assertContains(response, 'id="connections-weekly-total"')
        self.assertContains(response, "invite-date-mode")
        self.assertContains(response, "FullCalendar.Calendar")
        self.assertContains(response, "firstDay: 1")
        self.assertContains(response, "editable: true")
        self.assertContains(response, "eventClick(info)")
        self.assertContains(response, 'id="connection-edit-modal"')
        self.assertContains(response, 'id="connection-meeting-at" type="datetime-local" autocomplete="off"', html=False)
        self.assertContains(response, 'id="connection-invite-date-display"', html=False)
        self.assertContains(response, 'id="connection-edit-form" class="connection-edit-dialog" autocomplete="off"', html=False)
        self.assertContains(response, 'meetingAtInput.classList.toggle("hidden", inviteMode)')
        self.assertContains(response, 'id="connection-meeting-end"')
        self.assertContains(response, 'id="connection-description"')
        self.assertContains(response, 'id="connection-rating"')
        self.assertContains(response, 'id="connection-notes"')
        self.assertContains(response, 'id="connection-edit-delete"')
        self.assertNotContains(response, "Sync to Google Calendar")
        self.assertContains(response, 'id="connection-directions-button"')
        self.assertContains(response, 'id="directions-panel"')
        self.assertContains(response, "direction-delete-button")
        self.assertContains(response, ">Description<")
        self.assertContains(response, "eventDrop(info)")
        self.assertContains(response, "draggedMeetingTimes(info)")
        self.assertContains(response, "eventDateTimeInputValue(event)")
        self.assertContains(response, "info.revert()")
        self.assertContains(response, "window.alert(error.message)")
        self.assertContains(response, 'event.target.closest(".connection-panels")')
        self.assertContains(response, reverse("connection_events"))

    def test_connection_events_returns_only_scheduled_connections(self):
        scheduled_at = datetime(2026, 9, 15, 14, 20, tzinfo=UTC)
        scheduled = ProfessionalConnect.objects.create(
            professional=self.professional,
            invite_date=date(2026, 9, 1),
            meeting_at=scheduled_at,
            description="Career discussion",
        )
        ProfessionalConnect.objects.create(
            professional=self.professional,
            invite_date=date(2026, 9, 2),
        )

        response = self.client.get(reverse("connection_events"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            [
                {
                    "id": str(scheduled.pk),
                    "title": "Career discussion",
                    "start": "2026-09-15T08:20:00",
                    "end": "2026-09-15T09:20:00",
                    "allDay": False,
                    "extendedProps": {
                        "status": scheduled.status,
                        "description": "Career discussion",
                        "rating": None,
                        "notes": "",
                    },
                }
            ],
        )

    @patch("app.views.sync_professional_connect")
    def test_calendar_update_rejects_overlapping_meeting_before_google_sync(
        self, mock_sync
    ):
        mountain_timezone = ZoneInfo("America/Denver")
        ProfessionalConnect.objects.create(
            professional=self.professional,
            description="Existing connection",
            meeting_at=datetime(2026, 9, 15, 9, 0, tzinfo=mountain_timezone),
            meeting_end=datetime(2026, 9, 15, 10, 0, tzinfo=mountain_timezone),
        )
        connection = ProfessionalConnect.objects.create(
            professional=self.professional,
            description="Moved connection",
            meeting_at=datetime(2026, 9, 15, 11, 0, tzinfo=mountain_timezone),
            meeting_end=datetime(2026, 9, 15, 12, 0, tzinfo=mountain_timezone),
        )
        csrf_client = Client(enforce_csrf_checks=True)
        page_response = csrf_client.get(reverse("connections"))
        csrf_token = page_response.cookies["csrftoken"].value

        response = csrf_client.post(
            reverse("update_connection_meeting"),
            data=json.dumps(
                {
                    "id": connection.pk,
                    "start": "2026-09-15T09:30:00",
                    "meeting_end": "2026-09-15T10:30:00",
                }
            ),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("conflicts with", response.json()["error"])
        connection.refresh_from_db()
        self.assertEqual(
            timezone.localtime(connection.meeting_at, mountain_timezone),
            datetime(2026, 9, 15, 11, 0, tzinfo=mountain_timezone),
        )
        mock_sync.assert_not_called()

    @patch("app.views.sync_professional_connect")
    def test_connection_event_update_saves_then_syncs_to_google_calendar(self, mock_sync):
        connection = ProfessionalConnect.objects.create(
            professional=self.professional,
            meeting_at=datetime(2026, 9, 15, 16, 30, tzinfo=UTC),
        )
        mock_sync.return_value = {
            "meeting": {"status": "updated", "message": "Meeting updated."},
        }
        csrf_client = Client(enforce_csrf_checks=True)
        page_response = csrf_client.get(reverse("connections"))
        csrf_token = page_response.cookies["csrftoken"].value
        updated_at = datetime(2026, 9, 20, 18, 45, tzinfo=UTC)

        response = csrf_client.post(
            reverse("update_connection_meeting"),
            data=json.dumps(
                {
                    "id": connection.pk,
                    "start": updated_at.isoformat(),
                    "description": "Follow-up call",
                    "rating": 4,
                    "notes": "Discussed next steps.",
                    "meeting_end": "2026-09-20T20:15:00+00:00",
                }
            ),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(response.status_code, 200)
        connection.refresh_from_db()
        self.assertEqual(connection.meeting_at, updated_at)
        self.assertEqual(
            connection.meeting_end,
            datetime(2026, 9, 20, 20, 15, tzinfo=UTC),
        )
        self.assertEqual(connection.description, "Follow-up call")
        self.assertEqual(connection.rating, 4)
        self.assertEqual(connection.notes, "Discussed next steps.")
        self.assertEqual(response.json()["status"], connection.status)
        self.assertEqual(
            response.json()["sync_message"],
            "Connection saved and synchronized to Google Calendar.",
        )
        self.assertFalse(response.json()["sync_failed"])
        mock_sync.assert_called_once_with(connection)

    @patch("app.views.sync_professional_connect")
    def test_connection_event_update_preserves_save_when_google_sync_fails(self, mock_sync):
        connection = ProfessionalConnect.objects.create(
            professional=self.professional,
            meeting_at=datetime(2026, 9, 15, 16, 30, tzinfo=UTC),
        )
        mock_sync.return_value = {
            "meeting": {"status": "error", "message": "Google API unavailable."},
        }
        csrf_client = Client(enforce_csrf_checks=True)
        page_response = csrf_client.get(reverse("connections"))
        csrf_token = page_response.cookies["csrftoken"].value

        response = csrf_client.post(
            reverse("update_connection_meeting"),
            data=json.dumps(
                {
                    "id": connection.pk,
                    "start": "2026-09-20T18:45:00+00:00",
                    "meeting_end": "2026-09-20T19:45:00+00:00",
                    "notes": "Saved locally",
                }
            ),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["sync_message"],
            "Connection saved, but Google Calendar sync failed.",
        )
        self.assertTrue(response.json()["sync_failed"])
        connection.refresh_from_db()
        self.assertEqual(connection.notes, "Saved locally")

    @patch("app.views.sync_professional_connect")
    def test_connection_event_update_interprets_naive_datetime_as_mountain_time(
        self, mock_sync
    ):
        connection = ProfessionalConnect.objects.create(professional=self.professional)
        mock_sync.return_value = {
            "meeting": {"status": "created", "message": "Meeting created."}
        }
        csrf_client = Client(enforce_csrf_checks=True)
        page_response = csrf_client.get(reverse("connections"))
        csrf_token = page_response.cookies["csrftoken"].value

        response = csrf_client.post(
            reverse("update_connection_meeting"),
            data=json.dumps(
                {
                    "id": connection.pk,
                    "start": "2026-09-10T08:20",
                }
            ),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(response.status_code, 200)
        connection.refresh_from_db()
        self.assertEqual(
            timezone.localtime(connection.meeting_at, ZoneInfo("America/Denver")),
            datetime(2026, 9, 10, 8, 20, tzinfo=ZoneInfo("America/Denver")),
        )

    @patch("app.views.sync_professional_connect")
    def test_connection_event_date_update_preserves_mountain_clock_times(
        self, mock_sync
    ):
        mountain_timezone = ZoneInfo("America/Denver")
        connection = ProfessionalConnect.objects.create(
            professional=self.professional,
            meeting_at=datetime(2026, 9, 10, 8, 20, tzinfo=mountain_timezone),
            meeting_end=datetime(2026, 9, 10, 9, 20, tzinfo=mountain_timezone),
        )
        mock_sync.return_value = {
            "meeting": {"status": "updated", "message": "Meeting updated."}
        }
        csrf_client = Client(enforce_csrf_checks=True)
        page_response = csrf_client.get(reverse("connections"))
        csrf_token = page_response.cookies["csrftoken"].value

        response = csrf_client.post(
            reverse("update_connection_meeting"),
            data=json.dumps(
                {
                    "id": connection.pk,
                    "start": "2026-09-11T08:20:00",
                    "meeting_end": "2026-09-11T09:20:00",
                }
            ),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(response.status_code, 200)
        connection.refresh_from_db()
        self.assertEqual(
            timezone.localtime(connection.meeting_at, mountain_timezone),
            datetime(2026, 9, 11, 8, 20, tzinfo=mountain_timezone),
        )
        self.assertEqual(
            timezone.localtime(connection.meeting_end, mountain_timezone),
            datetime(2026, 9, 11, 9, 20, tzinfo=mountain_timezone),
        )
        mock_sync.assert_called_once_with(connection)

    def test_connection_events_supports_all_day_invite_date_mode(self):
        connection = ProfessionalConnect.objects.create(
            professional=self.professional,
            invite_date=date(2026, 9, 15),
            description="Invite conversation",
        )
        ProfessionalConnect.objects.create(
            professional=self.professional,
            meeting_at=datetime(2026, 9, 16, 16, 30, tzinfo=UTC),
            description="Meeting only",
        )

        response = self.client.get(
            reverse("connection_events"),
            {"date_mode": "invite"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        event = response.json()[0]
        self.assertEqual(event["id"], str(connection.pk))
        self.assertEqual(event["title"], "Invite conversation")
        self.assertEqual(event["start"], "2026-09-15")
        self.assertTrue(event["allDay"])

    def test_connection_events_split_invites_by_relationship_type(self):
        recruiter = Recruiter.objects.create(name="Calendar Recruiter")
        professional_invite = Connect.objects.create(
            professional=self.professional,
            invite_date=date(2026, 9, 15),
            description="Professional invite",
        )
        recruiter_invite = Connect.objects.create(
            recruiter=recruiter,
            invite_date=date(2026, 9, 15),
            description="Recruiter invite",
        )

        professional_response = self.client.get(
            reverse("connection_events"),
            {"date_mode": "invite-professionals"},
        )
        recruiter_response = self.client.get(
            reverse("connection_events"),
            {"date_mode": "invite-recruiters"},
        )

        self.assertEqual(
            [event["id"] for event in professional_response.json()],
            [str(professional_invite.pk)],
        )
        self.assertEqual(
            [event["id"] for event in recruiter_response.json()],
            [str(recruiter_invite.pk)],
        )

    def test_connection_weekly_total_uses_the_active_date_mode(self):
        today = timezone.localdate()
        week_start = today - timedelta(days=today.weekday())
        in_week_meeting = datetime.combine(
            week_start,
            datetime.min.time(),
            tzinfo=ZoneInfo("America/Denver"),
        )
        ProfessionalConnect.objects.create(
            professional=self.professional,
            meeting_at=in_week_meeting,
        )
        ProfessionalConnect.objects.create(
            professional=self.professional,
            invite_date=week_start + timedelta(days=1),
        )
        ProfessionalConnect.objects.create(
            professional=self.professional,
            invite_date=week_start - timedelta(days=1),
        )

        meeting_response = self.client.get(reverse("connection_weekly_total"))
        invite_response = self.client.get(
            reverse("connection_weekly_total"),
            {"date_mode": "invite"},
        )

        self.assertEqual(meeting_response.json(), {"total": 1})
        self.assertEqual(invite_response.json(), {"total": 1})

    @patch("app.views.sync_professional_connect")
    def test_connection_invite_date_update_requires_csrf_and_updates_invite_date(
        self, mock_sync
    ):
        meeting_at = datetime(2026, 9, 15, 16, 30, tzinfo=UTC)
        connection = ProfessionalConnect.objects.create(
            professional=self.professional,
            invite_date=date(2026, 9, 1),
            meeting_at=meeting_at,
        )
        mock_sync.return_value = {
            "meeting": {"status": "updated", "message": "Meeting updated."}
        }
        csrf_client = Client(enforce_csrf_checks=True)
        page_response = csrf_client.get(reverse("connections"))
        csrf_token = page_response.cookies["csrftoken"].value

        response = csrf_client.post(
            reverse("update_connection_meeting"),
            data=json.dumps(
                {
                    "id": connection.pk,
                    "start": "2026-09-20",
                    "date_mode": "invite",
                }
            ),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(response.status_code, 200)
        connection.refresh_from_db()
        self.assertEqual(connection.invite_date, date(2026, 9, 20))
        self.assertEqual(connection.meeting_at, meeting_at)

    @patch("app.views.delete_meeting_event")
    def test_connection_event_delete_requires_csrf_and_deletes_connection(
        self, mock_delete_meeting_event
    ):
        connection = ProfessionalConnect.objects.create(
            professional=self.professional,
            meeting_at=datetime(2026, 9, 15, 16, 30, tzinfo=UTC),
            google_meeting_event_id="google-event-id",
        )
        csrf_client = Client(enforce_csrf_checks=True)
        page_response = csrf_client.get(reverse("connections"))
        csrf_token = page_response.cookies["csrftoken"].value

        response = csrf_client.post(
            reverse("delete_connection"),
            data=json.dumps({"id": connection.pk}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(ProfessionalConnect.objects.filter(pk=connection.pk).exists())
        mock_delete_meeting_event.assert_called_once()

    @patch("app.views.sync_professional_connect")
    def test_connection_event_update_removes_google_event_when_meeting_is_cleared(
        self, mock_sync
    ):
        connection = ProfessionalConnect.objects.create(
            professional=self.professional,
            meeting_at=datetime(2026, 9, 15, 16, 30, tzinfo=UTC),
            google_meeting_event_id="google-event-id",
        )
        mock_sync.return_value = {
            "meeting": {
                "status": "deleted",
                "message": "Meeting deleted from Google Calendar.",
            },
        }
        csrf_client = Client(enforce_csrf_checks=True)
        page_response = csrf_client.get(reverse("connections"))
        csrf_token = page_response.cookies["csrftoken"].value

        response = csrf_client.post(
            reverse("update_connection_meeting"),
            data=json.dumps(
                {"id": connection.pk, "start": "", "clear_meeting": True}
            ),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["removed_from_calendar"])
        connection.refresh_from_db()
        self.assertIsNone(connection.meeting_at)
        self.assertIsNone(connection.meeting_end)
        mock_sync.assert_called_once_with(connection)

    def test_connection_directions_can_be_loaded_added_and_resolved(self):
        connection = ProfessionalConnect.objects.create(
            professional=self.professional,
            meeting_at=datetime(2026, 9, 15, 16, 30, tzinfo=UTC),
        )
        direction = Direction.objects.create(
            connect=connection,
            description="Review the portfolio.",
        )

        response = self.client.get(
            reverse("connection_directions", args=[connection.pk])
        )

        self.assertEqual(
            response.json(),
            {
                "directions": [
                    {
                        "id": direction.pk,
                        "description": "Review the portfolio.",
                        "resolved": False,
                    }
                ]
            },
        )

        csrf_client = Client(enforce_csrf_checks=True)
        page_response = csrf_client.get(reverse("connections"))
        csrf_token = page_response.cookies["csrftoken"].value
        add_response = csrf_client.post(
            reverse("connection_directions", args=[connection.pk]),
            data=json.dumps({"description": "Send follow-up questions."}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(add_response.status_code, 200)
        new_direction = Direction.objects.get(description="Send follow-up questions.")
        self.assertEqual(new_direction.connect, connection)

        update_response = csrf_client.post(
            reverse("update_direction", args=[direction.pk]),
            data=json.dumps({"resolved": True}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(update_response.status_code, 200)
        direction.refresh_from_db()
        self.assertTrue(direction.resolved)

        delete_response = csrf_client.post(
            reverse("delete_direction", args=[direction.pk]),
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(Direction.objects.filter(pk=direction.pk).exists())


class GoogleCalendarSyncTests(TestCase):
    def setUp(self):
        self.professional = Professional.objects.create(name="Calendar Professional")

    def test_professional_connect_defaults_meeting_end_to_one_hour(self):
        meeting_at = datetime(2026, 9, 15, 16, 30, tzinfo=UTC)
        connection = ProfessionalConnect.objects.create(
            professional=self.professional,
            meeting_at=meeting_at,
        )
        custom_end = meeting_at + timedelta(hours=2)
        custom_connection = ProfessionalConnect.objects.create(
            professional=self.professional,
            meeting_at=meeting_at + timedelta(hours=2),
            meeting_end=custom_end + timedelta(hours=2),
        )
        no_meeting = ProfessionalConnect.objects.create(professional=self.professional)

        self.assertEqual(connection.meeting_end, meeting_at + timedelta(hours=1))
        self.assertEqual(
            custom_connection.meeting_end,
            custom_end + timedelta(hours=2),
        )
        self.assertIsNone(no_meeting.meeting_end)

    def test_meeting_overlap_validation_allows_adjacent_meetings(self):
        mountain_timezone = ZoneInfo("America/Denver")
        ProfessionalConnect.objects.create(
            professional=self.professional,
            description="First connection",
            meeting_at=datetime(2026, 9, 15, 9, 0, tzinfo=mountain_timezone),
            meeting_end=datetime(2026, 9, 15, 10, 0, tzinfo=mountain_timezone),
        )
        adjacent = ProfessionalConnect.objects.create(
            professional=self.professional,
            description="Adjacent connection",
            meeting_at=datetime(2026, 9, 15, 10, 0, tzinfo=mountain_timezone),
            meeting_end=datetime(2026, 9, 15, 11, 0, tzinfo=mountain_timezone),
        )
        conflicting = ProfessionalConnect(
            professional=self.professional,
            description="Overlapping connection",
            meeting_at=datetime(2026, 9, 15, 9, 30, tzinfo=mountain_timezone),
        )

        with self.assertRaises(ValidationError) as error:
            conflicting.save()

        self.assertIsNotNone(adjacent.pk)
        self.assertIn("First connection", str(error.exception))
        self.assertIn("conflicts with", str(error.exception))

    def test_meeting_sync_creates_then_updates_one_google_event(self):
        meeting_at = datetime(2026, 9, 15, 16, 30, tzinfo=UTC)
        connection = ProfessionalConnect.objects.create(
            professional=self.professional,
            description="Ian x Calendar Professional",
            meeting_at=meeting_at,
        )
        service = MagicMock()
        service.events.return_value.insert.return_value.execute.return_value = {
            "id": "meeting-event-id"
        }

        created_result = sync_meeting_event(connection, service=service)

        self.assertEqual(created_result["status"], "created")
        connection.refresh_from_db()
        self.assertEqual(connection.google_meeting_event_id, "meeting-event-id")
        insert_body = service.events.return_value.insert.call_args.kwargs["body"]
        self.assertEqual(insert_body["summary"], "Ian x Calendar Professional")
        self.assertEqual(
            insert_body["start"]["dateTime"],
            timezone.localtime(meeting_at, ZoneInfo("America/Denver")).isoformat(),
        )
        self.assertEqual(
            insert_body["end"]["dateTime"],
            timezone.localtime(
                meeting_at + timedelta(hours=1), ZoneInfo("America/Denver")
            ).isoformat(),
        )
        self.assertEqual(insert_body["start"]["timeZone"], "America/Denver")
        self.assertEqual(insert_body["end"]["timeZone"], "America/Denver")

        updated_result = sync_meeting_event(connection, service=service)

        self.assertEqual(updated_result["status"], "updated")
        service.events.return_value.update.assert_called_once_with(
            calendarId="primary",
            eventId="meeting-event-id",
            body=insert_body,
        )

    def test_meeting_sync_deletes_linked_event_when_meeting_is_removed(self):
        connection = ProfessionalConnect.objects.create(
            professional=self.professional,
            google_meeting_event_id="meeting-event-id",
        )
        service = MagicMock()

        result = sync_meeting_event(connection, service=service)

        self.assertEqual(result["status"], "deleted")
        service.events.return_value.delete.assert_called_once_with(
            calendarId="primary",
            eventId="meeting-event-id",
        )
        connection.refresh_from_db()
        self.assertEqual(connection.google_meeting_event_id, "")

    @patch("app.services.google_calendar.get_calendar_service")
    def test_invite_only_connection_does_not_sync_to_google_calendar(self, mock_service):
        connection = ProfessionalConnect.objects.create(
            professional=self.professional,
            description="Ian x Calendar Professional",
            invite_date=date(2026, 9, 15),
        )

        result = sync_professional_connect(connection)

        self.assertEqual(result["meeting"]["status"], "skipped")
        connection.refresh_from_db()
        self.assertEqual(connection.google_invite_event_id, "")
        mock_service.assert_not_called()


class SkillPageTests(TestCase):
    def test_skills_page_shows_add_delete_header_and_add_button(self):
        Skill.objects.create(name="Python", type="Language")

        response = self.client.get(reverse("skills"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Resume")
        self.assertContains(response, "Add/Delete")
        self.assertContains(response, "Skill 1 of 1")
        self.assertContains(response, 'name="add_skill" value="1"', html=False)
        self.assertContains(response, 'name="delete_skill"', html=False)
        self.assertContains(response, 'name="new-resume_ready"', html=False)
        self.assertContains(response, 'name="form-0-resume_ready"', html=False)
        self.assertNotContains(response, ">New<", html=False)

    def test_skills_page_uses_arrow_navigation_labels(self):
        Skill.objects.create(name="Alpha", type="Language")
        Skill.objects.create(name="Beta", type="Technology")

        response = self.client.get(reverse("skills"), {"page": 1})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Skill 1 of 2")
        self.assertContains(response, 'aria-label="Next skill"', html=False)
        self.assertContains(response, "&rarr;", html=False)
        self.assertNotContains(response, '">Next<', html=False)
        self.assertNotContains(response, '">Previous<', html=False)

    def test_search_skill_form_filters_table_by_skill_id_without_pagination(self):
        python_skill = Skill.objects.create(name="Python", type="Language")
        sql_skill = Skill.objects.create(name="SQL", type="Technology")

        response = self.client.get(reverse("skills"), {"skill_id": sql_skill.pk})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Search Skill")
        self.assertContains(response, f'name="skill_id" value="{sql_skill.pk}"', html=False)
        self.assertContains(response, 'list="skill-search-options"', html=False)
        self.assertContains(response, f'<option value="Python" data-skill-id="{python_skill.pk}"></option>', html=False)
        self.assertContains(response, f'<option value="SQL" data-skill-id="{sql_skill.pk}"></option>', html=False)
        self.assertContains(response, "SQL")
        self.assertNotContains(response, "Skill 1 of", html=False)
        self.assertNotContains(response, 'aria-label="Next skill"', html=False)

    def test_search_skill_options_are_alphabetized_by_name(self):
        Skill.objects.create(name="Zulu", type="Technology")
        Skill.objects.create(name="Alpha", type="Language")
        Skill.objects.create(name="Mike", type="Domain")

        response = self.client.get(reverse("skills"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertLess(content.index('<option value="Alpha"'), content.index('<option value="Mike"'))
        self.assertLess(content.index('<option value="Mike"'), content.index('<option value="Zulu"'))

    def test_selected_skill_shows_roles_without_and_with_skill_in_side_by_side_tables(self):
        selected_skill = Skill.objects.create(name="SQL", type="Technology")
        other_skill = Skill.objects.create(name="Python", type="Language")
        company = Company.objects.create(name="Example Company")
        role_without_skill = Role.objects.create(
            company=company,
            title="Analyst",
            start_date="2024-01-01",
        )
        role_with_skill = Role.objects.create(
            company=company,
            title="Engineer",
            start_date="2024-01-01",
        )
        role_with_other_skill = Role.objects.create(
            company=company,
            title="Manager",
            start_date="2024-01-01",
        )
        role_with_skill.skills.add(selected_skill)
        role_with_other_skill.skills.add(other_skill)

        response = self.client.get(reverse("skills"), {"skill_id": selected_skill.pk})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [role.pk for role in response.context["roles_without_skill"]],
            [role_without_skill.pk, role_with_other_skill.pk],
        )
        self.assertEqual(
            [role.pk for role in response.context["roles_with_skill"]],
            [role_with_skill.pk],
        )
        self.assertContains(response, "Roles Without Skill")
        self.assertContains(response, "Roles With Skill")
        self.assertContains(response, "<td>Analyst</td>", html=True)
        self.assertContains(response, "<td>Engineer</td>", html=True)
        self.assertContains(response, "<td>Manager</td>", html=True)
        self.assertContains(response, 'name="role_without_skill_')
        self.assertContains(response, 'name="role_with_skill_')
        self.assertContains(response, "Projects")

    def test_displayed_skill_is_used_for_role_tables_when_no_skill_is_selected(self):
        displayed_skill = Skill.objects.create(name="Alpha", type="Technology")
        Skill.objects.create(name="Zulu", type="Language")
        company = Company.objects.create(name="Example Company")
        role_without_skill = Role.objects.create(
            company=company,
            title="Analyst",
            start_date="2024-01-01",
        )
        role_with_skill = Role.objects.create(
            company=company,
            title="Engineer",
            start_date="2024-01-01",
        )
        role_with_skill.skills.add(displayed_skill)

        response = self.client.get(reverse("skills"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [role.pk for role in response.context["roles_without_skill"]],
            [role_without_skill.pk],
        )
        self.assertEqual(
            [role.pk for role in response.context["roles_with_skill"]],
            [role_with_skill.pk],
        )
        self.assertContains(response, "<td>Analyst</td>", html=True)
        self.assertContains(response, "<td>Engineer</td>", html=True)

    def test_selected_skill_shows_projects_without_and_with_skill(self):
        selected_skill = Skill.objects.create(name="SQL", type="Technology")
        other_skill = Skill.objects.create(name="Python", type="Language")
        project_without_skill = Project.objects.create(title="Alpha Project")
        project_with_skill = Project.objects.create(title="Beta Project")
        project_with_other_skill = Project.objects.create(title="Gamma Project")
        project_with_skill.skills.add(selected_skill)
        project_with_other_skill.skills.add(other_skill)

        response = self.client.get(reverse("skills"), {"skill_id": selected_skill.pk})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [project.pk for project in response.context["projects_without_skill"]],
            [project_without_skill.pk, project_with_other_skill.pk],
        )
        self.assertEqual(
            [project.pk for project in response.context["projects_with_skill"]],
            [project_with_skill.pk],
        )
        self.assertContains(response, "Projects Without Skill")
        self.assertContains(response, "Projects With Skill")
        self.assertContains(response, "<td>Alpha Project</td>", html=True)
        self.assertContains(response, "<td>Beta Project</td>", html=True)
        self.assertContains(response, "<td>Gamma Project</td>", html=True)
        self.assertContains(response, 'name="project_without_skill_')
        self.assertContains(response, 'name="project_with_skill_')

    def test_selected_skill_shows_platform_boxes_using_platformskill_filters(self):
        selected_skill = Skill.objects.create(name="SQL", type="Technology")
        platform_not_listed_true_false = Platform.objects.create(name="Alpha Platform")
        platform_not_listed_null_null = Platform.objects.create(name="Beta Platform")
        platform_listed = Platform.objects.create(name="Gamma Platform")
        platform_unavailable = Platform.objects.create(name="Delta Platform")
        platform_other_skill = Platform.objects.create(name="Epsilon Platform")
        other_skill = Skill.objects.create(name="Python", type="Language")

        PlatformSkill.objects.create(
            platform=platform_not_listed_true_false,
            skill=selected_skill,
            available=True,
            listed=False,
        )
        PlatformSkill.objects.create(
            platform=platform_not_listed_null_null,
            skill=selected_skill,
            available=None,
            listed=None,
        )
        PlatformSkill.objects.create(
            platform=platform_listed,
            skill=selected_skill,
            available=True,
            listed=True,
        )
        PlatformSkill.objects.create(
            platform=platform_unavailable,
            skill=selected_skill,
            available=False,
            listed=False,
        )
        PlatformSkill.objects.create(
            platform=platform_other_skill,
            skill=other_skill,
            available=True,
            listed=False,
        )

        response = self.client.get(reverse("skills"), {"skill_id": selected_skill.pk})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item.platform.pk for item in response.context["platforms_not_listed"]],
            [platform_not_listed_true_false.pk, platform_not_listed_null_null.pk],
        )
        self.assertEqual(
            [item.platform.pk for item in response.context["platforms_listed"]],
            [platform_listed.pk],
        )
        self.assertContains(response, "Platforms")
        self.assertContains(response, "Available / Not Listed")
        self.assertContains(response, "Available / Listed")
        self.assertContains(response, "Alpha Platform")
        self.assertContains(response, "Beta Platform")
        self.assertContains(response, "Gamma Platform")
        self.assertContains(
            response,
            f'href="{reverse("skills")}?skill_id={selected_skill.pk}&platform_id={platform_listed.pk}"',
            html=False,
        )

    def test_displayed_skill_is_used_for_platform_boxes_when_no_skill_is_selected(self):
        displayed_skill = Skill.objects.create(name="Alpha", type="Technology")
        Skill.objects.create(name="Zulu", type="Language")
        platform_not_listed = Platform.objects.create(name="Alpha Platform")
        platform_listed = Platform.objects.create(name="Beta Platform")

        PlatformSkill.objects.create(
            platform=platform_not_listed,
            skill=displayed_skill,
            available=True,
            listed=False,
        )
        PlatformSkill.objects.create(
            platform=platform_listed,
            skill=displayed_skill,
            available=True,
            listed=True,
        )

        response = self.client.get(reverse("skills"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item.platform.pk for item in response.context["platforms_not_listed"]],
            [platform_not_listed.pk],
        )
        self.assertEqual(
            [item.platform.pk for item in response.context["platforms_listed"]],
            [platform_listed.pk],
        )
        self.assertContains(response, "Alpha Platform")
        self.assertContains(response, "Beta Platform")

    def test_selected_skill_and_platform_show_bottom_skill_boxes_with_requested_ordering(self):
        selected_skill = Skill.objects.create(name="SQL", type="Technology", rating=2)
        platform = Platform.objects.create(name="Target Platform")
        high_rating_not_listed = Skill.objects.create(name="Python", type="Language", rating=5)
        same_rating_not_listed_a = Skill.objects.create(name="AWS", type="Technology", rating=4)
        same_rating_not_listed_b = Skill.objects.create(name="Django", type="Technology", rating=4)
        listed_low = Skill.objects.create(name="Excel", type="Technology", rating=1)
        listed_high = Skill.objects.create(name="Bash", type="Language", rating=3)
        excluded_unavailable = Skill.objects.create(name="Cobol", type="Language", rating=5)

        PlatformSkill.objects.create(platform=platform, skill=selected_skill, available=True, listed=True)
        PlatformSkill.objects.create(platform=platform, skill=high_rating_not_listed, available=True, listed=False)
        PlatformSkill.objects.create(platform=platform, skill=same_rating_not_listed_a, available=None, listed=False)
        PlatformSkill.objects.create(platform=platform, skill=same_rating_not_listed_b, available=True, listed=None)
        PlatformSkill.objects.create(platform=platform, skill=listed_low, available=True, listed=True)
        PlatformSkill.objects.create(platform=platform, skill=listed_high, available=True, listed=True)
        PlatformSkill.objects.create(platform=platform, skill=excluded_unavailable, available=False, listed=False)

        response = self.client.get(
            reverse("skills"),
            {"skill_id": selected_skill.pk, "platform_id": platform.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item.skill.pk for item in response.context["skills_not_listed"]],
            [
                high_rating_not_listed.pk,
                same_rating_not_listed_a.pk,
                same_rating_not_listed_b.pk,
            ],
        )
        self.assertEqual(
            [item.skill.pk for item in response.context["skills_listed"]],
            [
                listed_low.pk,
                selected_skill.pk,
                listed_high.pk,
            ],
        )
        self.assertContains(response, "Skills Not Listed")
        self.assertContains(response, "Skills Listed")
        self.assertNotContains(response, f'name="platform_skill_name_', html=False)
        self.assertContains(response, f"{high_rating_not_listed.name} ({high_rating_not_listed.rating})")
        self.assertContains(response, f"{same_rating_not_listed_a.name} ({same_rating_not_listed_a.rating})")
        self.assertContains(response, f"{same_rating_not_listed_b.name} ({same_rating_not_listed_b.rating})")
        self.assertContains(response, f"{listed_low.name} ({listed_low.rating})")
        self.assertContains(response, f"{selected_skill.name} ({selected_skill.rating})")
        self.assertContains(response, f"{listed_high.name} ({listed_high.rating})")
        self.assertContains(
            response,
            f'href="{reverse("skills")}?skill_id={high_rating_not_listed.pk}&platform_id={platform.pk}"',
            html=False,
        )
        self.assertContains(response, 'target="_blank"', html=False)
        self.assertContains(response, "<th>Swap</th>", html=False)
        self.assertContains(
            response,
            f'name="platform_skill_not_listed_{high_rating_not_listed.platformskill_set.get(platform=platform).pk}"',
            html=False,
        )
        self.assertContains(
            response,
            f'name="platform_skill_listed_{selected_skill.platformskill_set.get(platform=platform).pk}"',
            html=False,
        )
        self.assertNotContains(
            response,
            f'name="platform_skill_rating_{high_rating_not_listed.platformskill_set.get(platform=platform).pk}"',
            html=False,
        )
        self.assertContains(
            response,
            '<tr style="background: #d9ead3;">',
            html=False,
        )

    def test_platforms_section_save_updates_selected_skill_date_and_swaps_listing(self):
        selected_skill = Skill.objects.create(name="SQL", type="Technology", rating=2)
        platform = Platform.objects.create(name="Target Platform")
        editable_skill = Skill.objects.create(name="Python", type="Language", rating=5)
        listed_skill = Skill.objects.create(name="Bash", type="Language", rating=3)
        editable_platform_skill = PlatformSkill.objects.create(
            platform=platform,
            skill=editable_skill,
            available=True,
            listed=False,
            updated=None,
        )
        listed_platform_skill = PlatformSkill.objects.create(
            platform=platform,
            skill=listed_skill,
            available=True,
            listed=True,
            updated=None,
        )
        untouched_platform_skill = PlatformSkill.objects.create(
            platform=platform,
            skill=selected_skill,
            available=True,
            listed=True,
            updated=None,
        )

        response = self.client.post(
            reverse("skills"),
            data={
                "form-TOTAL_FORMS": "1",
                "form-INITIAL_FORMS": "1",
                "form-MIN_NUM_FORMS": "0",
                "form-MAX_NUM_FORMS": "1000",
                "form-0-id": str(selected_skill.pk),
                "form-0-name": selected_skill.name,
                "form-0-type": selected_skill.type,
                "form-0-rating": str(selected_skill.rating),
                "skill_id": str(selected_skill.pk),
                "platform_id": str(platform.pk),
                "save_platform_skills": "1",
                f"platform_skill_available_{editable_platform_skill.pk}": "false",
                f"platform_skill_not_listed_{editable_platform_skill.pk}": "on",
                f"platform_skill_available_{listed_platform_skill.pk}": "",
                f"platform_skill_listed_{listed_platform_skill.pk}": "on",
                f"platform_skill_available_{untouched_platform_skill.pk}": "true",
            },
        )

        self.assertRedirects(
            response,
            f"{reverse('skills')}?skill_id={selected_skill.pk}&platform_id={platform.pk}",
        )
        editable_platform_skill.refresh_from_db()
        listed_platform_skill.refresh_from_db()
        untouched_platform_skill.refresh_from_db()
        self.assertEqual(editable_platform_skill.skill.name, "Python")
        self.assertEqual(editable_platform_skill.skill.rating, 5)
        self.assertFalse(editable_platform_skill.available)
        self.assertTrue(editable_platform_skill.listed)
        self.assertEqual(str(editable_platform_skill.updated), "2026-09-04")
        self.assertEqual(listed_platform_skill.skill.name, "Bash")
        self.assertEqual(listed_platform_skill.skill.rating, 3)
        self.assertIsNone(listed_platform_skill.available)
        self.assertFalse(listed_platform_skill.listed)
        self.assertEqual(str(listed_platform_skill.updated), "2026-09-04")
        self.assertTrue(untouched_platform_skill.listed)
        self.assertEqual(str(untouched_platform_skill.updated), "2026-09-04")

    def test_selected_skill_shows_platform_skill_formset_table_scoped_to_skill(self):
        selected_skill = Skill.objects.create(name="SQL", type="Technology")
        other_skill = Skill.objects.create(name="Python", type="Language")
        alpha_platform = Platform.objects.create(name="Alpha Platform", url="https://alpha.example.com")
        beta_platform = Platform.objects.create(name="Beta Platform", url="https://beta.example.com")
        gamma_platform = Platform.objects.create(name="Gamma Platform")

        alpha_platform_skill = PlatformSkill.objects.create(
            platform=alpha_platform,
            skill=selected_skill,
            available=True,
            listed=False,
            updated=None,
        )
        beta_platform_skill = PlatformSkill.objects.create(
            platform=beta_platform,
            skill=selected_skill,
            available=False,
            listed=True,
            updated="2026-08-15",
        )
        PlatformSkill.objects.create(
            platform=gamma_platform,
            skill=other_skill,
            available=True,
            listed=True,
            updated="2026-08-16",
        )

        response = self.client.get(reverse("skills"), {"skill_id": selected_skill.pk})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(
                response.context["selected_skill_platform_skill_formset"].queryset.values_list(
                    "pk",
                    flat=True,
                )
            ),
            [alpha_platform_skill.pk, beta_platform_skill.pk],
        )
        self.assertContains(response, "Platform Skills")
        self.assertContains(response, "Alpha Platform")
        self.assertContains(response, "Beta Platform")
        self.assertNotContains(response, "Gamma Platform")
        self.assertNotContains(response, "<th>Skill</th>", html=False)
        self.assertContains(
            response,
            'href="https://alpha.example.com"',
            html=False,
        )
        self.assertContains(
            response,
            'target="_blank"',
            html=False,
        )
        self.assertContains(
            response,
            'rel="noopener noreferrer"',
            html=False,
        )
        self.assertContains(
            response,
            'href="https://beta.example.com"',
            html=False,
        )
        self.assertContains(
            response,
            '<tr style="background: #f4cccc;">',
            html=False,
        )

    @patch("app.views.timezone.now")
    def test_selected_skill_platform_skill_formset_highlights_rows_by_updated_date(self, mock_now):
        mock_now.return_value = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
        selected_skill = Skill.objects.create(name="SQL", type="Technology")
        today_platform = Platform.objects.create(name="Today Platform", url="https://today.example.com")
        stale_platform = Platform.objects.create(name="Stale Platform", url="https://stale.example.com")
        recent_no_platform = Platform.objects.create(name="Recent No Platform")
        null_platform = Platform.objects.create(name="Null Platform", url="https://null.example.com")

        PlatformSkill.objects.create(
            platform=today_platform,
            skill=selected_skill,
            available=True,
            listed=True,
            updated="2026-09-04",
        )
        PlatformSkill.objects.create(
            platform=stale_platform,
            skill=selected_skill,
            available=True,
            listed=False,
            updated="2026-09-03",
        )
        PlatformSkill.objects.create(
            platform=recent_no_platform,
            skill=selected_skill,
            available=False,
            listed=False,
            updated="2026-09-03",
        )
        PlatformSkill.objects.create(
            platform=null_platform,
            skill=selected_skill,
            available=False,
            listed=False,
            updated=None,
        )

        response = self.client.get(reverse("skills"), {"skill_id": selected_skill.pk})

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<tr style="background: #d9ead3;">',
            html=False,
        )
        self.assertContains(
            response,
            '<tr style="background: #f4cccc;">',
            html=False,
            count=2,
        )
        self.assertContains(
            response,
            'name="selected-skill-platform-skills-0-available"',
            html=False,
        )
        self.assertContains(
            response,
            'name="selected-skill-platform-skills-0-listed"',
            html=False,
        )
        self.assertContains(
            response,
            'name="selected-skill-platform-skills-0-updated"',
            html=False,
        )
        html = response.content.decode()
        recent_no_index = html.index("Recent No Platform")
        recent_no_row = html[html.rfind("<tr", 0, recent_no_index):html.find("</tr>", recent_no_index)]
        self.assertNotIn("background: #f4cccc;", recent_no_row)

    @patch("app.views.timezone.now")
    def test_selected_feature_platform_features_only_mark_unavailable_rows_red_when_stale_or_null(self, mock_now):
        mock_now.return_value = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
        feature = Feature.objects.create(name="Billing")
        stale_yes_platform = Platform.objects.create(name="Stale Yes Platform")
        recent_no_platform = Platform.objects.create(name="Recent No Feature Platform")
        stale_no_platform = Platform.objects.create(name="Stale No Feature Platform")
        null_no_platform = Platform.objects.create(name="Null No Feature Platform")

        PlatformFeature.objects.create(
            platform=stale_yes_platform,
            feature=feature,
            available=True,
            updated="2026-09-03",
        )
        PlatformFeature.objects.create(
            platform=recent_no_platform,
            feature=feature,
            available=False,
            updated="2026-09-03",
        )
        PlatformFeature.objects.create(
            platform=stale_no_platform,
            feature=feature,
            available=False,
            updated="2025-09-04",
        )
        PlatformFeature.objects.create(
            platform=null_no_platform,
            feature=feature,
            available=False,
            updated=None,
        )

        response = self.client.get(reverse("features"), {"feature_id": feature.pk})

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<tr style="background: #f4cccc;">',
            html=False,
            count=3,
        )
        html = response.content.decode()
        recent_no_index = html.index("Recent No Feature Platform")
        recent_no_row = html[html.rfind("<tr", 0, recent_no_index):html.find("</tr>", recent_no_index)]
        self.assertNotIn("background: #f4cccc;", recent_no_row)

    def test_selected_skill_platform_skill_formset_save_updates_only_chosen_skill_rows(self):
        selected_skill = Skill.objects.create(name="SQL", type="Technology")
        other_skill = Skill.objects.create(name="Python", type="Language")
        alpha_platform = Platform.objects.create(name="Alpha Platform")
        beta_platform = Platform.objects.create(name="Beta Platform")
        gamma_platform = Platform.objects.create(name="Gamma Platform")

        alpha_platform_skill = PlatformSkill.objects.create(
            platform=alpha_platform,
            skill=selected_skill,
            available=True,
            listed=False,
            updated=None,
        )
        beta_platform_skill = PlatformSkill.objects.create(
            platform=beta_platform,
            skill=selected_skill,
            available=False,
            listed=True,
            updated="2026-08-15",
        )
        other_platform_skill = PlatformSkill.objects.create(
            platform=gamma_platform,
            skill=other_skill,
            available=True,
            listed=True,
            updated="2026-08-16",
        )

        response = self.client.post(
            reverse("skills"),
            data={
                "form-TOTAL_FORMS": "1",
                "form-INITIAL_FORMS": "1",
                "form-MIN_NUM_FORMS": "0",
                "form-MAX_NUM_FORMS": "1000",
                "form-0-id": str(selected_skill.pk),
                "form-0-name": selected_skill.name,
                "form-0-type": selected_skill.type,
                "form-0-rating": str(selected_skill.rating),
                "skill_id": str(selected_skill.pk),
                "page": "1",
                "selected-skill-platform-skills-TOTAL_FORMS": "2",
                "selected-skill-platform-skills-INITIAL_FORMS": "2",
                "selected-skill-platform-skills-MIN_NUM_FORMS": "0",
                "selected-skill-platform-skills-MAX_NUM_FORMS": "1000",
                "selected-skill-platform-skills-0-id": str(alpha_platform_skill.pk),
                "selected-skill-platform-skills-0-available": "false",
                "selected-skill-platform-skills-0-listed": "true",
                "selected-skill-platform-skills-0-updated": "2026-09-03",
                "selected-skill-platform-skills-1-id": str(beta_platform_skill.pk),
                "selected-skill-platform-skills-1-available": "",
                "selected-skill-platform-skills-1-listed": "",
                "selected-skill-platform-skills-1-updated": "",
                "save_selected_skill_platform_skills": "1",
            },
        )

        self.assertRedirects(response, f"{reverse('skills')}?skill_id={selected_skill.pk}")
        alpha_platform_skill.refresh_from_db()
        beta_platform_skill.refresh_from_db()
        other_platform_skill.refresh_from_db()
        self.assertFalse(alpha_platform_skill.available)
        self.assertTrue(alpha_platform_skill.listed)
        self.assertEqual(str(alpha_platform_skill.updated), "2026-09-03")
        self.assertIsNone(beta_platform_skill.available)
        self.assertIsNone(beta_platform_skill.listed)
        self.assertIsNone(beta_platform_skill.updated)
        self.assertTrue(other_platform_skill.available)
        self.assertTrue(other_platform_skill.listed)
        self.assertEqual(str(other_platform_skill.updated), "2026-08-16")

    def test_selected_skill_shows_courses_grouped_by_education(self):
        selected_skill = Skill.objects.create(name="SQL", type="Technology")
        school_one = School.objects.create(name="School One")
        school_two = School.objects.create(name="School Two")
        education_one = Education.objects.create(
            school=school_one,
            degree="Bachelor of Science",
            field_of_study="Computer Science",
        )
        education_two = Education.objects.create(
            school=school_two,
            degree="Master of Science",
            field_of_study="Analytics",
        )
        course_without_skill = Course.objects.create(
            education=education_one,
            title="Algorithms",
            sort_order=1,
        )
        course_with_skill = Course.objects.create(
            education=education_one,
            title="Databases",
            sort_order=2,
        )
        other_education_course = Course.objects.create(
            education=education_two,
            title="Statistics",
            sort_order=1,
        )
        course_with_skill.skills.add(selected_skill)

        response = self.client.get(reverse("skills"), {"skill_id": selected_skill.pk})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["course_groups"]), 2)
        first_group = next(
            group for group in response.context["course_groups"]
            if group["education"].pk == education_one.pk
        )
        second_group = next(
            group for group in response.context["course_groups"]
            if group["education"].pk == education_two.pk
        )
        self.assertEqual(
            [course.pk for course in first_group["courses_without_skill"]],
            [course_without_skill.pk],
        )
        self.assertEqual(
            [course.pk for course in first_group["courses_with_skill"]],
            [course_with_skill.pk],
        )
        self.assertEqual(
            [course.pk for course in second_group["courses_without_skill"]],
            [other_education_course.pk],
        )
        self.assertEqual(
            [course.pk for course in second_group["courses_with_skill"]],
            [],
        )
        self.assertContains(response, "Courses")
        self.assertContains(response, "Courses Without Skill")
        self.assertContains(response, "Courses With Skill")
        self.assertContains(response, "School One | Bachelor of Science | Computer Science")
        self.assertContains(response, "School Two | Master of Science | Analytics")
        self.assertContains(response, f'name="swap_courses" value="{education_one.pk}"', html=False)
        self.assertContains(response, f'name="swap_courses" value="{education_two.pk}"', html=False)
        self.assertContains(response, "<td>Algorithms</td>", html=True)
        self.assertContains(response, "<td>Databases</td>", html=True)
        self.assertContains(response, "<td>Statistics</td>", html=True)
        self.assertContains(response, 'name="course_without_skill_')
        self.assertContains(response, 'name="course_with_skill_')

    def test_swap_button_adds_and_removes_selected_skill_for_checked_roles(self):
        selected_skill = Skill.objects.create(name="SQL", type="Technology")
        company = Company.objects.create(name="Example Company")
        role_without_skill = Role.objects.create(
            company=company,
            title="Analyst",
            start_date="2024-01-01",
        )
        role_with_skill = Role.objects.create(
            company=company,
            title="Engineer",
            start_date="2024-01-01",
        )
        role_with_skill.skills.add(selected_skill)

        response = self.client.post(
            reverse("skills"),
            data={
                "form-TOTAL_FORMS": "1",
                "form-INITIAL_FORMS": "1",
                "form-MIN_NUM_FORMS": "0",
                "form-MAX_NUM_FORMS": "1000",
                "form-0-id": str(selected_skill.pk),
                "form-0-name": selected_skill.name,
                "form-0-type": selected_skill.type,
                "form-0-rating": str(selected_skill.rating),
                "skill_id": str(selected_skill.pk),
                "page": "1",
                "swap_roles": "1",
                f"role_without_skill_{role_without_skill.pk}": "on",
                f"role_with_skill_{role_with_skill.pk}": "on",
            },
        )

        self.assertRedirects(response, f"{reverse('skills')}?skill_id={selected_skill.pk}")
        self.assertTrue(role_without_skill.skills.filter(pk=selected_skill.pk).exists())
        self.assertFalse(role_with_skill.skills.filter(pk=selected_skill.pk).exists())

    def test_swap_button_uses_displayed_skill_when_no_selected_skill_is_provided(self):
        displayed_skill = Skill.objects.create(name="Alpha", type="Technology")
        Skill.objects.create(name="Zulu", type="Language")
        company = Company.objects.create(name="Example Company")
        role_without_skill = Role.objects.create(
            company=company,
            title="Analyst",
            start_date="2024-01-01",
        )
        role_with_skill = Role.objects.create(
            company=company,
            title="Engineer",
            start_date="2024-01-01",
        )
        role_with_skill.skills.add(displayed_skill)

        response = self.client.post(
            reverse("skills"),
            data={
                "form-TOTAL_FORMS": "1",
                "form-INITIAL_FORMS": "1",
                "form-MIN_NUM_FORMS": "0",
                "form-MAX_NUM_FORMS": "1000",
                "form-0-id": str(displayed_skill.pk),
                "form-0-name": displayed_skill.name,
                "form-0-type": displayed_skill.type,
                "form-0-rating": str(displayed_skill.rating),
                "page": "1",
                "swap_roles": "1",
                f"role_without_skill_{role_without_skill.pk}": "on",
                f"role_with_skill_{role_with_skill.pk}": "on",
            },
        )

        self.assertRedirects(response, f"{reverse('skills')}?page=1")
        self.assertTrue(role_without_skill.skills.filter(pk=displayed_skill.pk).exists())
        self.assertFalse(role_with_skill.skills.filter(pk=displayed_skill.pk).exists())

    def test_swap_button_adds_and_removes_selected_skill_for_checked_projects(self):
        selected_skill = Skill.objects.create(name="SQL", type="Technology")
        project_without_skill = Project.objects.create(title="Alpha Project")
        project_with_skill = Project.objects.create(title="Beta Project")
        project_with_skill.skills.add(selected_skill)

        response = self.client.post(
            reverse("skills"),
            data={
                "form-TOTAL_FORMS": "1",
                "form-INITIAL_FORMS": "1",
                "form-MIN_NUM_FORMS": "0",
                "form-MAX_NUM_FORMS": "1000",
                "form-0-id": str(selected_skill.pk),
                "form-0-name": selected_skill.name,
                "form-0-type": selected_skill.type,
                "form-0-rating": str(selected_skill.rating),
                "skill_id": str(selected_skill.pk),
                "page": "1",
                "swap_projects": "1",
                f"project_without_skill_{project_without_skill.pk}": "on",
                f"project_with_skill_{project_with_skill.pk}": "on",
            },
        )

        self.assertRedirects(response, f"{reverse('skills')}?skill_id={selected_skill.pk}")
        self.assertTrue(project_without_skill.skills.filter(pk=selected_skill.pk).exists())
        self.assertFalse(project_with_skill.skills.filter(pk=selected_skill.pk).exists())

    def test_swap_button_adds_and_removes_selected_skill_for_checked_courses(self):
        selected_skill = Skill.objects.create(name="SQL", type="Technology")
        school = School.objects.create(name="School One")
        education = Education.objects.create(
            school=school,
            degree="Bachelor of Science",
            field_of_study="Computer Science",
        )
        course_without_skill = Course.objects.create(
            education=education,
            title="Algorithms",
        )
        course_with_skill = Course.objects.create(
            education=education,
            title="Databases",
        )
        course_with_skill.skills.add(selected_skill)

        response = self.client.post(
            reverse("skills"),
            data={
                "form-TOTAL_FORMS": "1",
                "form-INITIAL_FORMS": "1",
                "form-MIN_NUM_FORMS": "0",
                "form-MAX_NUM_FORMS": "1000",
                "form-0-id": str(selected_skill.pk),
                "form-0-name": selected_skill.name,
                "form-0-type": selected_skill.type,
                "form-0-rating": str(selected_skill.rating),
                "skill_id": str(selected_skill.pk),
                "page": "1",
                "swap_courses": str(education.pk),
                f"course_without_skill_{course_without_skill.pk}": "on",
                f"course_with_skill_{course_with_skill.pk}": "on",
            },
        )

        self.assertRedirects(response, f"{reverse('skills')}?skill_id={selected_skill.pk}")
        self.assertTrue(course_without_skill.skills.filter(pk=selected_skill.pk).exists())
        self.assertFalse(course_with_skill.skills.filter(pk=selected_skill.pk).exists())

    def test_add_skill_button_creates_skill_and_redirects(self):
        response = self.client.post(
            reverse("skills"),
            data={
                "form-TOTAL_FORMS": "0",
                "form-INITIAL_FORMS": "0",
                "form-MIN_NUM_FORMS": "0",
                "form-MAX_NUM_FORMS": "1000",
                "page": "1",
                "new-name": "Python",
                "new-type": "Language",
                "new-rating": "5",
                "new-resume_ready": "on",
                "add_skill": "1",
            },
        )

        created_skill = Skill.objects.get(name="Python")
        self.assertRedirects(response, f"{reverse('skills')}?skill_id={created_skill.pk}")
        self.assertEqual(created_skill.type, "Language")
        self.assertEqual(created_skill.rating, 5)
        self.assertTrue(created_skill.resume_ready)
        self.assertIsNone(created_skill.updated)

    def test_add_skill_with_invalid_name_returns_error_on_page(self):
        existing_skill = Skill.objects.create(name="Existing Skill", type="Technology")

        response = self.client.post(
            reverse("skills"),
            data={
                "form-TOTAL_FORMS": "1",
                "form-INITIAL_FORMS": "1",
                "form-MIN_NUM_FORMS": "0",
                "form-MAX_NUM_FORMS": "1000",
                "form-0-id": str(existing_skill.pk),
                "form-0-name": existing_skill.name,
                "form-0-type": existing_skill.type,
                "form-0-rating": str(existing_skill.rating),
                "form-0-updated": "",
                "page": "1",
                "new-name": "   ",
                "new-type": "Language",
                "new-rating": "3",
                "new-updated": "",
                "add_skill": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid Name")
        self.assertContains(response, 'style="color: red;"', html=False)
        self.assertEqual(Skill.objects.filter(name="Existing Skill").count(), 1)
        self.assertEqual(Skill.objects.count(), 1)

    def test_delete_skill_button_removes_existing_skill(self):
        existing_skill = Skill.objects.create(name="Existing Skill", type="Technology")

        response = self.client.post(
            reverse("skills"),
            data={
                "form-TOTAL_FORMS": "1",
                "form-INITIAL_FORMS": "1",
                "form-MIN_NUM_FORMS": "0",
                "form-MAX_NUM_FORMS": "1000",
                "form-0-id": str(existing_skill.pk),
                "form-0-name": existing_skill.name,
                "form-0-type": existing_skill.type,
                "form-0-rating": str(existing_skill.rating),
                "form-0-updated": "",
                "page": "1",
                "skill_id": str(existing_skill.pk),
                "delete_skill": str(existing_skill.pk),
            },
        )

        self.assertRedirects(response, reverse("skills"))
        self.assertFalse(Skill.objects.filter(pk=existing_skill.pk).exists())

    def test_save_button_does_not_add_top_row_skill_and_sets_updated_on_existing_skill(self):
        existing_skill = Skill.objects.create(name="Existing Skill", type="Technology")

        response = self.client.post(
            reverse("skills"),
            data={
                "form-TOTAL_FORMS": "1",
                "form-INITIAL_FORMS": "1",
                "form-MIN_NUM_FORMS": "0",
                "form-MAX_NUM_FORMS": "1000",
                "form-0-id": str(existing_skill.pk),
                "form-0-name": "Edited Skill",
                "form-0-type": "Domain",
                "form-0-rating": "4",
                "form-0-resume_ready": "on",
                "page": "1",
                "new-name": "Should Not Be Added",
                "new-type": "Language",
            },
        )

        self.assertRedirects(response, f"{reverse('skills')}?page=1")
        existing_skill.refresh_from_db()
        self.assertEqual(existing_skill.name, "Edited Skill")
        self.assertEqual(existing_skill.type, "Domain")
        self.assertEqual(existing_skill.rating, 4)
        self.assertTrue(existing_skill.resume_ready)
        self.assertEqual(str(existing_skill.updated), "2026-09-04")
        self.assertFalse(Skill.objects.filter(name="Should Not Be Added").exists())

    def test_save_button_sets_updated_on_unchanged_existing_skill(self):
        existing_skill = Skill.objects.create(
            name="Existing Skill",
            type="Technology",
            updated=None,
        )

        response = self.client.post(
            reverse("skills"),
            data={
                "form-TOTAL_FORMS": "1",
                "form-INITIAL_FORMS": "1",
                "form-MIN_NUM_FORMS": "0",
                "form-MAX_NUM_FORMS": "1000",
                "form-0-id": str(existing_skill.pk),
                "form-0-name": existing_skill.name,
                "form-0-type": existing_skill.type,
                "form-0-rating": str(existing_skill.rating),
                "form-0-resume_ready": "on",
                "page": "1",
            },
        )

        self.assertRedirects(response, f"{reverse('skills')}?page=1")
        existing_skill.refresh_from_db()
        self.assertEqual(str(existing_skill.updated), "2026-09-04")


class FeaturePageTests(TestCase):
    def test_features_page_shows_single_existing_feature_row_with_pagination_and_search(self):
        first_feature = Feature.objects.create(
            name="Auth",
            updated="2026-09-01",
            wait=timedelta(days=10),
        )
        second_feature = Feature.objects.create(
            name="Billing",
            updated="2026-09-01",
            wait=timedelta(days=1),
        )
        third_feature = Feature.objects.create(name="Catalog")

        response = self.client.get(reverse("features"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<title>Features</title>", html=False)
        self.assertContains(response, f'href="{reverse("features")}"', html=False)
        self.assertContains(response, "<h1>Features</h1>", html=False)
        self.assertContains(response, "Due Date")
        self.assertContains(response, "Add/Delete")
        self.assertContains(response, "Search Feature")
        self.assertContains(response, 'name="add_feature" value="1"', html=False)
        self.assertContains(response, f'name="delete_feature" value="{second_feature.pk}"', html=False)
        self.assertNotContains(response, f'name="delete_feature" value="{first_feature.pk}"', html=False)
        self.assertNotContains(response, f'name="delete_feature" value="{third_feature.pk}"', html=False)
        self.assertContains(response, 'name="form-0-name"', html=False)
        self.assertContains(response, 'name="form-0-wait_0"', html=False)
        self.assertContains(response, 'name="form-0-wait_1"', html=False)
        self.assertContains(response, 'name="form-0-wait_2"', html=False)
        self.assertContains(response, 'name="form-0-updated"', html=False)
        self.assertContains(response, 'name="new-name"', html=False)
        self.assertContains(response, 'name="new-wait_0"', html=False)
        self.assertContains(response, 'name="new-wait_1"', html=False)
        self.assertContains(response, 'name="new-wait_2"', html=False)
        self.assertContains(response, 'name="new-updated"', html=False)
        self.assertContains(response, 'name="feature_id" value=""', html=False)
        self.assertContains(response, 'list="feature-search-options"', html=False)
        self.assertContains(response, f'<option value="Billing" data-feature-id="{second_feature.pk}"></option>', html=False)
        self.assertContains(response, "placeholder=\"Months\"", html=False)
        self.assertContains(response, "placeholder=\"Weeks\"", html=False)
        self.assertContains(response, "placeholder=\"Days\"", html=False)
        self.assertContains(response, "Months")
        self.assertContains(response, "Weeks")
        self.assertContains(response, "Days")
        self.assertContains(response, 'id="%s" style="background: #f4cccc;"' % second_feature.pk, html=False)
        self.assertContains(response, "2026-09-02")
        self.assertNotContains(response, "2026-09-11")
        self.assertContains(response, ">Save</button>", html=False)
        self.assertContains(response, "Feature 1 of 3")
        self.assertContains(response, 'aria-label="Next feature"', html=False)
        self.assertContains(response, "&rarr;", html=False)
        self.assertNotContains(response, 'aria-label="Previous feature"', html=False)
        self.assertEqual(
            [form.instance.pk for form in response.context["formset"].forms],
            [second_feature.pk],
        )
        self.assertEqual(response.context["feature_page_obj"].number, 1)

    def test_features_page_paginates_to_next_feature(self):
        first_feature = Feature.objects.create(
            name="Auth",
            updated="2026-09-01",
            wait=timedelta(days=10),
        )
        second_feature = Feature.objects.create(
            name="Billing",
            updated="2026-09-01",
            wait=timedelta(days=1),
        )

        response = self.client.get(reverse("features"), {"page": 2})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'name="delete_feature" value="{first_feature.pk}"', html=False)
        self.assertNotContains(response, f'name="delete_feature" value="{second_feature.pk}"', html=False)
        self.assertContains(response, "Feature 2 of 2")
        self.assertContains(response, 'aria-label="Previous feature"', html=False)
        self.assertNotContains(response, 'aria-label="Next feature"', html=False)
        self.assertEqual([form.instance.pk for form in response.context["formset"].forms], [first_feature.pk])

    @patch("app.views.timezone.now")
    def test_features_page_marks_row_red_when_due_date_is_today(self, mock_now):
        mock_now.return_value = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
        feature = Feature.objects.create(
            name="Billing",
            updated="2026-09-03",
            wait=timedelta(days=1),
        )

        response = self.client.get(reverse("features"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'id="{feature.pk}" style="background: #f4cccc;"',
            html=False,
        )
        self.assertContains(response, "2026-09-04")

    def test_search_feature_form_filters_table_by_feature_id_without_pagination(self):
        first_feature = Feature.objects.create(name="Auth")
        second_feature = Feature.objects.create(name="Billing")

        response = self.client.get(reverse("features"), {"feature_id": second_feature.pk})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Search Feature")
        self.assertContains(response, f'name="feature_id" value="{second_feature.pk}"', html=False)
        self.assertContains(response, f'<option value="Auth" data-feature-id="{first_feature.pk}"></option>', html=False)
        self.assertContains(response, f'<option value="Billing" data-feature-id="{second_feature.pk}"></option>', html=False)
        self.assertContains(response, f'name="delete_feature" value="{second_feature.pk}"', html=False)
        self.assertNotContains(response, f'name="delete_feature" value="{first_feature.pk}"', html=False)
        self.assertNotContains(response, "Feature 1 of", html=False)
        self.assertNotContains(response, 'aria-label="Next feature"', html=False)

    def test_selected_feature_shows_links_section_scoped_to_feature(self):
        first_feature = Feature.objects.create(name="Auth")
        second_feature = Feature.objects.create(name="Billing")
        first_link = FeatureLink.objects.create(feature=first_feature, url="https://auth.example.com")
        second_link = FeatureLink.objects.create(feature=second_feature, url="https://billing.example.com")

        response = self.client.get(reverse("features"), {"feature_id": second_feature.pk})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<h2 style="margin: 0;">Links</h2>', html=False)
        self.assertContains(
            response,
            '<button type="button" class="feature-toggle-button" data-target="feature-links-section-body">Show</button>',
            html=False,
        )
        self.assertContains(response, '<div id="feature-links-section-body" class="hidden">', html=False)
        self.assertContains(response, 'name="feature-links-TOTAL_FORMS" value="1"', html=False)
        self.assertContains(response, 'name="new-link-url"', html=False)
        self.assertContains(response, 'name="add_feature_link" value="1"', html=False)
        self.assertContains(response, f'name="delete_feature_link" value="{second_link.pk}"', html=False)
        self.assertNotContains(response, f'name="delete_feature_link" value="{first_link.pk}"', html=False)
        self.assertContains(response, 'name="feature-links-0-url"', html=False)
        self.assertContains(
            response,
            '<a href="https://billing.example.com" target="_blank" rel="noopener noreferrer">https://billing.example.com</a>',
            html=False,
        )
        self.assertContains(response, 'value="https://billing.example.com"', html=False)
        self.assertNotContains(response, 'value="https://auth.example.com"', html=False)
        self.assertEqual(
            [form.instance.pk for form in response.context["feature_link_formset"].forms],
            [second_link.pk],
        )

    def test_selected_feature_shows_platforms_section_scoped_to_feature(self):
        first_feature = Feature.objects.create(name="Auth")
        second_feature = Feature.objects.create(name="Billing")
        first_platform = Platform.objects.create(name="Alpha", url="https://alpha.example.com")
        second_platform = Platform.objects.create(name="Beta")
        first_platform_feature = PlatformFeature.objects.create(
            platform=first_platform,
            feature=first_feature,
            available=True,
            updated="2026-09-02",
        )
        second_platform_feature = PlatformFeature.objects.create(
            platform=second_platform,
            feature=second_feature,
            available=False,
            updated="2026-09-04",
        )

        response = self.client.get(reverse("features"), {"feature_id": second_feature.pk})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<h2 style="margin: 0;">Platforms</h2>', html=False)
        self.assertContains(
            response,
            '<button type="button" class="feature-toggle-button" data-target="feature-platforms-section-body">Show</button>',
            html=False,
        )
        self.assertContains(response, '<div id="feature-platforms-section-body" class="hidden">', html=False)
        self.assertContains(response, '<h3 style="margin: 0;">Platform Features</h3>', html=False)
        self.assertContains(
            response,
            'name="selected-feature-platform-features-TOTAL_FORMS" value="1"',
            html=False,
        )
        self.assertContains(
            response,
            'name="save_selected_feature_platform_features" value="1"',
            html=False,
        )
        self.assertContains(
            response,
            '<tr style="background: #d9ead3;">',
            html=False,
        )
        self.assertNotContains(response, "Alpha", html=False)
        self.assertContains(response, "Beta")
        self.assertContains(response, 'name="selected-feature-platform-features-0-available"', html=False)
        self.assertContains(response, 'name="selected-feature-platform-features-0-updated"', html=False)
        self.assertNotContains(
            response,
            f'value="{first_platform_feature.pk}"',
            html=False,
        )
        self.assertEqual(
            [form.instance.pk for form in response.context["selected_feature_platform_feature_formset"].forms],
            [second_platform_feature.pk],
        )

    def test_links_section_uses_displayed_feature_when_feature_id_is_not_set(self):
        first_feature = Feature.objects.create(
            name="Auth",
            updated="2026-09-01",
            wait=timedelta(days=10),
        )
        displayed_feature = Feature.objects.create(
            name="Billing",
            updated="2026-09-01",
            wait=timedelta(days=1),
        )
        FeatureLink.objects.create(feature=first_feature, url="https://auth.example.com")
        displayed_link = FeatureLink.objects.create(
            feature=displayed_feature,
            url="https://billing.example.com",
        )

        response = self.client.get(reverse("features"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<h2 style="margin: 0;">Links</h2>', html=False)
        self.assertContains(response, '<div id="feature-links-section-body" class="hidden">', html=False)
        self.assertContains(response, f'name="delete_feature_link" value="{displayed_link.pk}"', html=False)
        self.assertNotContains(response, 'value="https://auth.example.com"', html=False)
        self.assertContains(
            response,
            '<a href="https://billing.example.com" target="_blank" rel="noopener noreferrer">https://billing.example.com</a>',
            html=False,
        )
        self.assertEqual(response.context["displayed_feature"].pk, displayed_feature.pk)
        self.assertEqual(
            [form.instance.pk for form in response.context["feature_link_formset"].forms],
            [displayed_link.pk],
        )

    def test_links_section_resolves_relative_link_text_from_base_url(self):
        feature = Feature.objects.create(name="Billing")
        relative_link = FeatureLink.objects.create(feature=feature, url="docs/guide")

        response = self.client.get(reverse("features"), {"feature_id": feature.pk})

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<a href="http://testserver/docs/guide" target="_blank" rel="noopener noreferrer">docs/guide</a>',
            html=False,
        )
        self.assertEqual(
            response.context["feature_link_formset"].forms[0].instance.resolved_url,
            "http://testserver/docs/guide",
        )
        self.assertEqual(response.context["feature_link_formset"].forms[0].instance.pk, relative_link.pk)

    def test_due_date_uses_calendar_month_addition(self):
        feature = Feature.objects.create(
            name="Addresses",
            updated="2026-03-04",
            wait=timedelta(days=180),
        )

        response = self.client.get(reverse("features"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2026-09-04")
        self.assertNotContains(response, "2026-08-31")
        feature_form = next(
            form for form in response.context["formset"].forms if form.instance.pk == feature.pk
        )
        self.assertEqual(str(feature_form.instance.due_date), "2026-09-04")

    def test_add_feature_button_creates_feature_and_redirects(self):
        first_platform = Platform.objects.create(name="Alpha Platform")
        second_platform = Platform.objects.create(name="Beta Platform")

        response = self.client.post(
            reverse("features"),
            data={
                "form-TOTAL_FORMS": "0",
                "form-INITIAL_FORMS": "0",
                "form-MIN_NUM_FORMS": "0",
                "form-MAX_NUM_FORMS": "1000",
                "new-name": "Search",
                "new-wait_0": "0",
                "new-wait_1": "2",
                "new-wait_2": "1",
                "new-updated": "2026-09-03",
                "add_feature": "1",
            },
        )

        created_feature = Feature.objects.get(name="Search")
        self.assertRedirects(
            response,
            f"{reverse('features')}?feature_id={created_feature.pk}",
            fetch_redirect_response=False,
        )
        self.assertEqual(str(created_feature.wait), "15 days, 0:00:00")
        self.assertEqual(str(created_feature.updated), "2026-09-03")
        self.assertEqual(
            set(
                PlatformFeature.objects.filter(feature=created_feature).values_list(
                    "platform_id",
                    flat=True,
                )
            ),
            {first_platform.pk, second_platform.pk},
        )

    def test_add_feature_link_button_creates_link_for_selected_feature(self):
        selected_feature = Feature.objects.create(name="Billing")
        other_feature = Feature.objects.create(name="Auth")

        response = self.client.post(
            reverse("features"),
            data={
                "form-TOTAL_FORMS": "1",
                "form-INITIAL_FORMS": "1",
                "form-MIN_NUM_FORMS": "0",
                "form-MAX_NUM_FORMS": "1000",
                "feature-links-TOTAL_FORMS": "0",
                "feature-links-INITIAL_FORMS": "0",
                "feature-links-MIN_NUM_FORMS": "0",
                "feature-links-MAX_NUM_FORMS": "1000",
                "page": "1",
                "feature_id": str(selected_feature.pk),
                "form-0-id": str(selected_feature.pk),
                "form-0-name": selected_feature.name,
                "form-0-wait_0": "",
                "form-0-wait_1": "",
                "form-0-wait_2": "",
                "form-0-updated": "",
                "new-link-url": "https://billing.example.com",
                "add_feature_link": "1",
            },
        )

        self.assertRedirects(response, f"{reverse('features')}?feature_id={selected_feature.pk}")
        self.assertTrue(
            FeatureLink.objects.filter(
                feature=selected_feature,
                url="https://billing.example.com",
            ).exists()
        )
        self.assertFalse(
            FeatureLink.objects.filter(
                feature=other_feature,
                url="https://billing.example.com",
            ).exists()
        )

    def test_delete_feature_button_removes_existing_feature(self):
        existing_feature = Feature.objects.create(name="Search")

        response = self.client.post(
            reverse("features"),
            data={
                "form-TOTAL_FORMS": "1",
                "form-INITIAL_FORMS": "1",
                "form-MIN_NUM_FORMS": "0",
                "form-MAX_NUM_FORMS": "1000",
                "page": "1",
                "feature_id": "",
                "form-0-id": str(existing_feature.pk),
                "form-0-name": existing_feature.name,
                "form-0-wait_0": "",
                "form-0-wait_1": "",
                "form-0-wait_2": "",
                "form-0-updated": "",
                "delete_feature": str(existing_feature.pk),
            },
        )

        self.assertRedirects(response, f"{reverse('features')}?page=1")
        self.assertFalse(Feature.objects.filter(pk=existing_feature.pk).exists())

    def test_delete_feature_link_button_removes_existing_link(self):
        selected_feature = Feature.objects.create(name="Billing")
        existing_link = FeatureLink.objects.create(
            feature=selected_feature,
            url="https://billing.example.com",
        )

        response = self.client.post(
            reverse("features"),
            data={
                "form-TOTAL_FORMS": "1",
                "form-INITIAL_FORMS": "1",
                "form-MIN_NUM_FORMS": "0",
                "form-MAX_NUM_FORMS": "1000",
                "feature-links-TOTAL_FORMS": "1",
                "feature-links-INITIAL_FORMS": "1",
                "feature-links-MIN_NUM_FORMS": "0",
                "feature-links-MAX_NUM_FORMS": "1000",
                "page": "1",
                "feature_id": str(selected_feature.pk),
                "form-0-id": str(selected_feature.pk),
                "form-0-name": selected_feature.name,
                "form-0-wait_0": "",
                "form-0-wait_1": "",
                "form-0-wait_2": "",
                "form-0-updated": "",
                "feature-links-0-id": str(existing_link.pk),
                "feature-links-0-url": existing_link.url,
                "delete_feature_link": str(existing_link.pk),
            },
        )

        self.assertRedirects(response, f"{reverse('features')}?feature_id={selected_feature.pk}")
        self.assertFalse(FeatureLink.objects.filter(pk=existing_link.pk).exists())

    def test_save_platforms_button_updates_existing_platform_features(self):
        selected_feature = Feature.objects.create(name="Billing")
        platform = Platform.objects.create(name="Alpha")
        platform_feature = PlatformFeature.objects.create(
            platform=platform,
            feature=selected_feature,
            available=None,
            updated=None,
        )

        response = self.client.post(
            reverse("features"),
            data={
                "form-TOTAL_FORMS": "1",
                "form-INITIAL_FORMS": "1",
                "form-MIN_NUM_FORMS": "0",
                "form-MAX_NUM_FORMS": "1000",
                "feature-links-TOTAL_FORMS": "0",
                "feature-links-INITIAL_FORMS": "0",
                "feature-links-MIN_NUM_FORMS": "0",
                "feature-links-MAX_NUM_FORMS": "1000",
                "selected-feature-platform-features-TOTAL_FORMS": "1",
                "selected-feature-platform-features-INITIAL_FORMS": "1",
                "selected-feature-platform-features-MIN_NUM_FORMS": "0",
                "selected-feature-platform-features-MAX_NUM_FORMS": "1000",
                "page": "1",
                "feature_id": str(selected_feature.pk),
                "form-0-id": str(selected_feature.pk),
                "form-0-name": selected_feature.name,
                "form-0-wait_0": "",
                "form-0-wait_1": "",
                "form-0-wait_2": "",
                "form-0-updated": "",
                "selected-feature-platform-features-0-id": str(platform_feature.pk),
                "selected-feature-platform-features-0-available": "true",
                "selected-feature-platform-features-0-updated": "2026-09-04",
                "save_selected_feature_platform_features": "1",
            },
        )

        self.assertRedirects(response, f"{reverse('features')}?feature_id={selected_feature.pk}")
        platform_feature.refresh_from_db()
        self.assertTrue(platform_feature.available)
        self.assertEqual(str(platform_feature.updated), "2026-09-04")

    def test_save_button_updates_existing_features(self):
        existing_feature = Feature.objects.create(name="Search")

        response = self.client.post(
            reverse("features"),
            data={
                "form-TOTAL_FORMS": "1",
                "form-INITIAL_FORMS": "1",
                "form-MIN_NUM_FORMS": "0",
                "form-MAX_NUM_FORMS": "1000",
                "page": "1",
                "feature_id": "",
                "form-0-id": str(existing_feature.pk),
                "form-0-name": "Search Updated",
                "form-0-wait_0": "1",
                "form-0-wait_1": "0",
                "form-0-wait_2": "2",
                "form-0-updated": "2026-09-03",
            },
        )

        self.assertRedirects(response, f"{reverse('features')}?page=1")
        existing_feature.refresh_from_db()
        self.assertEqual(existing_feature.name, "Search Updated")
        self.assertEqual(str(existing_feature.wait), "32 days, 0:00:00")
        self.assertEqual(str(existing_feature.updated), "2026-09-03")
