from django.contrib import admin
from .models import (Company, Role, RoleTask, Address, City,
                     State, Country, County, School, Education,
                     Project, ProjectTask, Skill, Course, Supervisor)


class RoleTaskInline(admin.TabularInline):
    model = RoleTask
    extra = 1
    filter_horizontal = ("skills",)


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")


@admin.register(State)
class StateAdmin(admin.ModelAdmin):
    list_display = ("name", "abbreviation", "country")
    search_fields = ("name", "abbreviation", "country__name")


@admin.register(County)
class CountyAdmin(admin.ModelAdmin):
    list_display = ("name", "state")
    search_fields = ("name", "state__name", "state__abbreviation")


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ("name", "state", "population")
    search_fields = ("name", "state__name", "state__abbreviation")


class CourseInline(admin.TabularInline):
    model = Course
    extra = 1
    ordering = ("sort_order",)
    filter_horizontal = ("skills",)


class SupervisorInline(admin.TabularInline):
    model = Supervisor
    extra = 1


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "company",
        "start_date",
        "end_date",
        "current",
        "starting_pay",
        "ending_pay",
        "pay_frequency",
        "is_public",
    )
    list_filter = ("current", "is_public", "company")
    search_fields = ("title", "company__name", "description")
    filter_horizontal = ("skills",)
    inlines = [RoleTaskInline, SupervisorInline]


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "website", "address")
    search_fields = ("name", "description")


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("street_1", "city", "postal_code")
    search_fields = ("street_1", "street_2", "postal_code")


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ("name", "website")
    search_fields = ("name",)


@admin.register(Education)
class EducationAdmin(admin.ModelAdmin):
    list_display = ("degree", "field_of_study", "school", "start_date", "end_date", "graduated")
    list_filter = ("graduated", "school")
    search_fields = ("degree", "field_of_study", "school__name", "description")
    inlines = [CourseInline]


class ProjectTaskInline(admin.TabularInline):
    model = ProjectTask
    extra = 1
    filter_horizontal = ("skills",)


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("title", "resume_ready", "is_public", "start_date", "end_date", "sort_order")
    list_filter = ("resume_ready", "is_public")
    search_fields = ("title", "short_description", "description")
    filter_horizontal = ("skills",)
    inlines = [ProjectTaskInline]


@admin.register(ProjectTask)
class ProjectTaskAdmin(admin.ModelAdmin):
    list_display = ("project", "short_description", "resume_ready", "sort_order")
    list_filter = ("resume_ready", "project")
    search_fields = ("description", "project__title")
    filter_horizontal = ("skills",)

    @staticmethod
    def short_description(obj):
        return obj.description[:80]






