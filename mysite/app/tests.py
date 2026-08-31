from unittest.mock import patch

from django.contrib.messages import get_messages
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from freelancersdk.resources.projects.exceptions import ProjectsNotFoundException

from .models import (
    Address,
    City,
    Company,
    Country,
    Course,
    Education,
    FreelancerProject,
    FreelancerSkill,
    Platform,
    PlatformSkill,
    Project,
    ProjectTask,
    Residency,
    Role,
    RoleTask,
    School,
    Skill,
    State,
    Supervisor,
)
from .views import (
    FREELANCER_RATE_LIMIT_MESSAGE,
    SEARCH_API_RESULT_LIMIT,
    _build_search_cache_key,
    _normalize_search_query,
)


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
        self.search_url = reverse("search")
        self.save_url = reverse("save_freelancer_project")

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
        self.company = Company.objects.create(name="Carroll College", address=self.address)
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

    def test_platform_skills_page_uses_paginated_formset_and_updates_existing_rows(self):
        platform_alpha = Platform.objects.create(name="Alpha Platform")
        platform_beta = Platform.objects.create(name="Beta Platform")

        platform_skill_null = PlatformSkill.objects.create(
            platform=platform_alpha,
            skill=self.python_skill,
            available=None,
            listed=None,
            updated=None,
        )
        platform_skill_dated = PlatformSkill.objects.create(
            platform=platform_beta,
            skill=self.sql_skill,
            available=True,
            listed=False,
            updated="2026-08-15",
        )

        response = self.client.get(reverse("platform_skills"))

        self.assertEqual(response.status_code, 200)
        page_items = list(response.context["page_obj"].object_list)
        self.assertEqual(
            [item.pk for item in page_items],
            [platform_skill_null.pk, platform_skill_dated.pk],
        )
        self.assertContains(response, "Platform Skills")
        self.assertContains(response, "Alpha Platform")
        self.assertContains(response, "Python")
        self.assertContains(response, "Beta Platform")
        self.assertContains(response, "SQL")
        self.assertContains(response, 'name="form-0-available"')
        self.assertContains(response, 'name="form-0-listed"')
        self.assertContains(response, 'name="form-0-updated"')
        self.assertContains(response, ">Unknown<", html=False)
        self.assertNotContains(response, "Delete")
        self.assertNotContains(response, ">New<", html=False)

        post_data = {
            "form-TOTAL_FORMS": "2",
            "form-INITIAL_FORMS": "2",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "page": "1",
            "form-0-id": str(platform_skill_null.pk),
            "form-0-available": "false",
            "form-0-listed": "true",
            "form-0-updated": "2026-08-20",
            "form-1-id": str(platform_skill_dated.pk),
            "form-1-available": "true",
            "form-1-listed": "false",
            "form-1-updated": "2026-08-15",
        }

        post_response = self.client.post(reverse("platform_skills"), data=post_data)

        self.assertRedirects(post_response, f"{reverse('platform_skills')}?page=1")

        platform_skill_null.refresh_from_db()
        platform_skill_dated.refresh_from_db()

        self.assertFalse(platform_skill_null.available)
        self.assertTrue(platform_skill_null.listed)
        self.assertEqual(str(platform_skill_null.updated), "2026-08-20")
        self.assertEqual(platform_skill_null.platform, platform_alpha)
        self.assertEqual(platform_skill_null.skill, self.python_skill)
        self.assertTrue(platform_skill_dated.available)
        self.assertFalse(platform_skill_dated.listed)
        self.assertEqual(str(platform_skill_dated.updated), "2026-08-15")
        self.assertEqual(PlatformSkill.objects.count(), 2)
