from django.db.models import Prefetch

from app.models import Course, Education, Project, ProjectTask, Role, RoleTask, Skill


def _date_range(start_date, end_date, current=False):
    start = start_date.strftime("%b %Y") if start_date else "Unknown start"
    end = "Present" if current else end_date.strftime("%b %Y") if end_date else "Unknown end"
    return f"{start} – {end}"


def _skills_text(skills):
    return ", ".join(skill.name for skill in skills)


def _append_detail(lines, label, value, indent="  "):
    value = (value or "").strip()
    if value:
        lines.append(f"{indent}{label}: {value}")


def build_candidate_background():
    """Build factual candidate context from resume-related Career app records."""
    educations = Education.objects.select_related("school").prefetch_related(
        Prefetch(
            "courses",
            queryset=Course.objects.prefetch_related(
                Prefetch("skills", queryset=Skill.objects.order_by("name"))
            ).order_by("sort_order", "title"),
        )
    ).order_by("-end_date", "-start_date", "school__name", "degree")
    roles = Role.objects.filter(is_public=True).select_related("company").prefetch_related(
        Prefetch("tasks", queryset=RoleTask.objects.order_by("sort_order", "pk")),
        Prefetch("skills", queryset=Skill.objects.order_by("name")),
    ).order_by("-start_date", "title")
    projects = Project.objects.filter(is_public=True).prefetch_related(
        Prefetch("tasks", queryset=ProjectTask.objects.order_by("sort_order", "pk")),
        Prefetch("skills", queryset=Skill.objects.order_by("name")),
    ).order_by("sort_order", "title")
    skills = Skill.objects.order_by("type", "name")

    lines = ["Candidate Background", "", "EDUCATION"]
    education_count = 0
    for education in educations:
        education_count += 1
        program = education.degree
        if education.field_of_study:
            program = f"{program}, {education.field_of_study}"
        lines.append(
            f"- {program} — {education.school.name} "
            f"({_date_range(education.start_date, education.end_date)})"
        )
        _append_detail(lines, "Description", education.description)
        courses = list(education.courses.all())
        if courses:
            lines.append("  Courses:")
            for course in courses:
                course_name = f"{course.code}: {course.title}" if course.code else course.title
                lines.append(f"    - {course_name}")
                _append_detail(lines, "Description", course.description, indent="      ")
                course_skills = _skills_text(course.skills.all())
                if course_skills:
                    lines.append(f"      Skills: {course_skills}")
    if not education_count:
        lines.append("- No education records available.")

    lines.extend(["", "PROFESSIONAL EXPERIENCE"])
    role_count = 0
    for role in roles:
        role_count += 1
        lines.append(
            f"- {role.title} — {role.company.name} "
            f"({_date_range(role.start_date, role.end_date, role.current)})"
        )
        _append_detail(lines, "Description", role.description)
        tasks = [task.description.strip() for task in role.tasks.all() if task.description.strip()]
        if tasks:
            lines.append("  Tasks:")
            lines.extend(f"    - {task}" for task in tasks)
        role_skills = _skills_text(role.skills.all())
        if role_skills:
            lines.append(f"  Skills: {role_skills}")
    if not role_count:
        lines.append("- No public role records available.")

    lines.extend(["", "PROJECTS"])
    project_count = 0
    for project in projects:
        project_count += 1
        lines.append(
            f"- {project.title} ({_date_range(project.start_date, project.end_date)})"
        )
        _append_detail(lines, "Short description", project.short_description)
        if project.description.strip() != project.short_description.strip():
            _append_detail(lines, "Description", project.description)
        tasks = [task.description.strip() for task in project.tasks.all() if task.description.strip()]
        if tasks:
            lines.append("  Tasks:")
            lines.extend(f"    - {task}" for task in tasks)
        project_skills = _skills_text(project.skills.all())
        if project_skills:
            lines.append(f"  Skills: {project_skills}")
    if not project_count:
        lines.append("- No public project records available.")

    lines.extend(["", "TECHNICAL SKILLS"])
    skill_count = 0
    for skill in skills:
        skill_count += 1
        details = [skill.type] if skill.type else []
        if skill.rating:
            details.append(f"rating {skill.rating}/5")
        suffix = f" ({'; '.join(details)})" if details else ""
        lines.append(f"- {skill.name}{suffix}")
    if not skill_count:
        lines.append("- No skill records available.")

    return "\n".join(lines)
