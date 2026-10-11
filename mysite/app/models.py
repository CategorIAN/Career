from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.utils.functional import cached_property
from calendar import monthrange
from datetime import timedelta
from zoneinfo import ZoneInfo
from django.db.models import Max, Q

MOUNTAIN_TIME_ZONE = ZoneInfo("America/Denver")


def _add_calendar_months(date_value, months):
    if not months:
        return date_value

    total_month_index = (date_value.month - 1) + months
    year = date_value.year + (total_month_index // 12)
    month = (total_month_index % 12) + 1
    day = min(date_value.day, monthrange(year, month)[1])
    return date_value.replace(year=year, month=month, day=day)


def _wait_parts(wait_value):
    total_days = wait_value.days
    months = total_days // 30
    remaining_days = total_days % 30
    weeks = remaining_days // 7
    days = remaining_days % 7
    return months, weeks, days


class Skill(models.Model):
    name = models.CharField(max_length=100, unique=True)

    SKILL_TYPES = [(x, x) for x in ["Language", "Technology", "Domain", "Other"]]

    type = models.CharField(
        max_length=50,
        choices=SKILL_TYPES,
        blank=True
    )

    rating = models.IntegerField(
        default=0,
        validators=[
            MinValueValidator(0),
            MaxValueValidator(5)
        ],
    )

    resume_ready = models.BooleanField(default=False)

    updated = models.DateField(blank=True, null=True)

    def __str__(self):
        return f"{self.name}"


class Country(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=3, unique=True)

    def __str__(self):
        return self.name


class State(models.Model):
    name = models.CharField(max_length=100)
    abbreviation = models.CharField(max_length=2, unique=True)
    country = models.ForeignKey("Country", on_delete=models.PROTECT)

    def __str__(self):
        return self.abbreviation


class County(models.Model):
    name = models.CharField(max_length=100)

    state = models.ForeignKey(
        "State",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    def __str__(self):
        if self.state:
            return f"{self.name} County, {self.state.abbreviation}"
        return self.name


class City(models.Model):
    name = models.CharField(max_length=100)

    state = models.ForeignKey(
        "State",
        on_delete=models.PROTECT,
    )

    county = models.ForeignKey(
        "County",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    population = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )

    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )

    website = models.URLField(blank=True)

    def __str__(self):
        return f"{self.name}, {self.state.abbreviation}"


class School(models.Model):
    name = models.CharField(max_length=200)
    city = models.ForeignKey(
        to="City",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    website = models.URLField(blank=True)

    def __str__(self):
        return self.name


class Education(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
    )

    degree = models.CharField(max_length=100)

    field_of_study = models.CharField(
        max_length=100,
        blank=True,
    )

    start_date = models.DateField(
        null=True,
        blank=True,
    )

    end_date = models.DateField(
        null=True,
        blank=True,
    )

    graduated = models.BooleanField(default=True)

    gpa = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        null=True,
        blank=True,
    )

    honors = models.CharField(
        max_length=200,
        blank=True,
    )

    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.degree} in {self.field_of_study} @ {self.school}"


class Address(models.Model):
    street_1 = models.CharField(max_length=200)

    street_2 = models.CharField(
        max_length=200,
        blank=True,
    )

    city = models.ForeignKey(
        "City",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    postal_code = models.CharField(
        max_length=20,
        blank=True,
    )

    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.street_1}, {self.city}"


class Company(models.Model):
    name = models.CharField(max_length=200)

    address = models.ForeignKey(
        "Address",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    website = models.URLField(blank=True)

    linkedin_url = models.URLField(blank=True)

    phone = models.CharField(
        max_length=30,
        blank=True,
    )

    email = models.EmailField(
        blank=True,
    )

    description = models.TextField(blank=True)
    job_search_enabled = models.BooleanField(default=True)
    supports_job_search_terms = models.BooleanField(default=True)

    @cached_property
    def last_applied(self):
        try:
            last_submitted = self.last_applied_submitted
        except AttributeError:
            last_submitted = self.applications.aggregate(
                last_submitted=Max("submitted")
            )["last_submitted"]

        if last_submitted is None:
            return None
        return timezone.now() - last_submitted

    @property
    def last_applied_days(self):
        if self.last_applied is None:
            return None
        return self.last_applied.days

    def __str__(self):
        return self.name


class Role(models.Model):
    company = models.ForeignKey(
        "Company",
        on_delete=models.PROTECT,
    )

    title = models.CharField(max_length=200)

    start_date = models.DateField()

    end_date = models.DateField(
        null=True,
        blank=True,
    )

    current = models.BooleanField(default=False)

    starting_pay = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )

    ending_pay = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )

    class PayFrequency(models.TextChoices):
        HOURLY = "hourly", "Hourly"
        MONTHLY = "monthly", "Monthly"

    pay_frequency = models.CharField(
        max_length=20,
        choices=PayFrequency.choices,
        blank=True,
    )

    reason_for_leaving = models.CharField(
        max_length=200,
        blank=True,
    )

    description = models.TextField(blank=True)

    is_public = models.BooleanField(default=True)

    skills = models.ManyToManyField("Skill", blank=True)

    def __str__(self):
        return self.title


class RoleTask(models.Model):
    role = models.ForeignKey("Role", related_name="tasks", on_delete=models.CASCADE)
    description = models.TextField()
    resume_ready = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)


class FreelancerSkill(models.Model):
    id = models.IntegerField(primary_key=True)
    name = models.CharField(max_length=100)
    category_id = models.IntegerField(null=True, blank=True)
    category_name = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self):
        return self.name


class FreelancerProject(models.Model):
    freelancer_id = models.BigIntegerField(unique=True)

    title = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=50)
    deleted = models.BooleanField(default=False)
    project_type = models.CharField(max_length=20)

    submitted_at = models.DateTimeField(null=True, blank=True)
    bid_period_days = models.IntegerField(null=True, blank=True)
    free_bids_expire_at = models.DateTimeField(null=True, blank=True)

    budget_min = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    budget_max = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    bid_count = models.IntegerField(null=True, blank=True)
    bid_avg = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    urgent = models.BooleanField(default=False)
    featured = models.BooleanField(default=False)
    nonpublic = models.BooleanField(default=False)
    enterprise = models.BooleanField(default=False)
    premium = models.BooleanField(default=False)
    sealed = models.BooleanField(default=False)
    nda_required = models.BooleanField(default=False)

    raw_json = models.JSONField(null=True, blank=True)

    imported_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    freelancer_skills = models.ManyToManyField(
        FreelancerSkill,
        related_name="projects",
        blank=True,
    )

    def __str__(self):
        return self.title


class Project(models.Model):
    title = models.CharField(max_length=200)

    short_description = models.CharField(
        max_length=300,
        blank=True,
    )

    description = models.TextField(blank=True)

    start_date = models.DateField(
        null=True,
        blank=True,
    )

    end_date = models.DateField(
        null=True,
        blank=True,
    )

    resume_ready = models.BooleanField(default=False)

    is_public = models.BooleanField(default=True)

    github_url = models.URLField(blank=True)

    live_url = models.URLField(blank=True)

    sort_order = models.PositiveIntegerField(default=0)

    skills = models.ManyToManyField(
        "Skill",
        blank=True,
        related_name="projects",
    )

    def __str__(self):
        return self.title


class ProjectTask(models.Model):
    project = models.ForeignKey(
        "Project",
        related_name="tasks",
        on_delete=models.CASCADE,
    )

    description = models.TextField()

    resume_ready = models.BooleanField(default=False)

    sort_order = models.PositiveIntegerField(default=0)


class Course(models.Model):
    education = models.ForeignKey(
        "Education",
        related_name="courses",
        on_delete=models.CASCADE,
    )

    title = models.CharField(max_length=200)

    code = models.CharField(
        max_length=50,
        blank=True,
    )

    description = models.TextField(blank=True)

    skills = models.ManyToManyField(
        "Skill",
        blank=True,
        related_name="courses",
    )

    grade = models.CharField(
        max_length=10,
        blank=True,
    )

    resume_ready = models.BooleanField(default=False)

    sort_order = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.title


class Supervisor(models.Model):
    role = models.ForeignKey(
        "Role",
        related_name="supervisors",
        on_delete=models.CASCADE,
    )

    name = models.CharField(max_length=200)

    title = models.CharField(
        max_length=200,
        blank=True,
    )

    email = models.EmailField(blank=True)

    phone = models.CharField(
        max_length=30,
        blank=True,
    )

    may_contact = models.BooleanField(default=False)

    notes = models.TextField(blank=True)

    def __str__(self):
        return self.name


class Reference(models.Model):
    name = models.CharField(max_length=200)

    role = models.ForeignKey(
        "Role",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    education = models.ForeignKey(
        "Education",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    title = models.CharField(max_length=200, blank=True)

    email = models.EmailField(blank=True)

    phone = models.CharField(max_length=30, blank=True)

    relationship = models.CharField(
        max_length=100,
        blank=True,
    )

    preferred = models.BooleanField(default=False)

    may_contact = models.BooleanField(default=False)

    notes = models.TextField(blank=True)


class Residency(models.Model):
    address = models.ForeignKey(
        "Address",
        on_delete=models.PROTECT,
    )

    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    current = models.BooleanField(default=False)

    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.address} ({self.start_date} - {self.end_date or 'Present'})"


class ProfileSetting(models.Model):
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return self.key


class Platform(models.Model):
    name = models.CharField(
        max_length=100,
        unique=True,
    )

    url = models.URLField(
        blank=True,
    )

    max_skills = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    skills = models.ManyToManyField(
        "Skill",
        through="PlatformSkill",
        related_name="platforms",
        blank=True,
    )

    features = models.ManyToManyField(
        "Feature",
        through="PlatformFeature",
        related_name="platforms",
        blank=True,
    )

    job_search_enabled = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class PlatformSkill(models.Model):
    platform = models.ForeignKey(
        "Platform",
        on_delete=models.CASCADE,
    )

    skill = models.ForeignKey(
        "Skill",
        on_delete=models.CASCADE,
    )

    available = models.BooleanField(
        blank=True,
        null=True
    )

    listed = models.BooleanField(
        blank=True,
        null=True
    )

    updated = models.DateField(
        null=True,
        blank=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["platform", "skill"],
                name="unique_platform_skill",
            )
        ]

    def __str__(self):
        return f"{self.platform} - {self.skill}"


class Feature(models.Model):
    name = models.CharField(
        max_length=200,
        unique=True,
    )

    updated = models.DateField(
        null=True,
        blank=True,
    )

    wait = models.DurationField(
        null=True,
        blank=True,
    )

    def __str__(self):
        return self.name


class FeatureLink(models.Model):
    feature = models.ForeignKey(
        "Feature",
        related_name="links",
        on_delete=models.CASCADE,
    )

    url = models.CharField(max_length=500)

    def __str__(self):
        return self.url


class PlatformFeature(models.Model):
    platform = models.ForeignKey(
        "Platform",
        on_delete=models.CASCADE,
    )

    feature = models.ForeignKey(
        "Feature",
        on_delete=models.CASCADE,
    )

    available = models.BooleanField(
        null=True,
        blank=True,
    )

    updated = models.DateField(
        null=True,
        blank=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["platform", "feature"],
                name="unique_platform_feature",
            )
        ]

    def __str__(self):
        return f"{self.platform} - {self.feature}"


class Professional(models.Model):
    name = models.CharField(max_length=200)

    linkedin_url = models.URLField(blank=True)

    phone = models.CharField(
        max_length=30,
        blank=True,
    )

    email = models.EmailField(blank=True)

    wait = models.DurationField(
        null=True,
        blank=True,
    )

    companies = models.ManyToManyField(
        "Company",
        related_name="professionals",
        blank=True,
    )

    referrals = models.ManyToManyField(
        "self",
        symmetrical=False,
        related_name="referred_by",
        blank=True,
    )

    def __str__(self):
        return self.name

    @cached_property
    def _connection_records(self):
        if self.pk is None:
            return []
        return list(self.connects.all())

    @cached_property
    def last_invited(self):
        invite_dates = (
            connection.invite_date
            for connection in self._connection_records
            if connection.invite_date is not None
        )
        return max(invite_dates, default=None)

    @cached_property
    def last_connected(self):
        meeting_times = (
            connection.meeting_at
            for connection in self._connection_records
            if connection.meeting_at is not None
        )
        return max(meeting_times, default=None)

    @cached_property
    def last_attended(self):
        if self.last_connected is None:
            return None
        return timezone.localtime(self.last_connected).date()

    @cached_property
    def invite_due(self):
        if self.last_invited is None:
            return None
        return _add_calendar_months(self.last_invited, 1)

    @cached_property
    def connect_due(self):
        if self.last_connected is None or self.wait is None:
            return None
        months, weeks, days = _wait_parts(self.wait)
        due_date = _add_calendar_months(
            timezone.localtime(self.last_connected, MOUNTAIN_TIME_ZONE).date(),
            months,
        )
        return due_date + timedelta(weeks=weeks, days=days)

    @cached_property
    def average_rating(self):
        ratings = [
            connection.rating
            for connection in self._connection_records
            if connection.rating is not None
        ]
        if not ratings:
            return None
        return sum(ratings) / len(ratings)

    @cached_property
    def average_rating_stars(self):
        if self.average_rating is None:
            return ""
        filled_stars = min(5, int(self.average_rating + 0.5))
        return f"{'★' * filled_stars}{'☆' * (5 - filled_stars)}"

    @cached_property
    def invite_success(self):
        if not self._connection_records:
            return None
        attended_connections = sum(
            connection.meeting_at is not None
            for connection in self._connection_records
        )
        return (attended_connections / len(self._connection_records)) * 100

    @property
    def invite(self):
        current_date = timezone.localdate()
        if self.wait is None:
            return False
        if self.invite_due is None:
            return True
        if self.connect_due is None:
            return self.invite_due <= current_date
        return (
                self.connect_due <= current_date
                and (
                        self.last_invited <= self.last_attended
                        or self.invite_due <= current_date
                )
        )


class Recruiter(models.Model):
    name = models.CharField(max_length=200)

    linkedin_url = models.URLField(blank=True)

    phone = models.CharField(
        max_length=30,
        blank=True,
    )

    email = models.EmailField(blank=True)

    wait = models.DurationField(
        null=True,
        blank=True,
    )

    companies = models.ManyToManyField(
        "Company",
        related_name="recruiters",
        blank=True,
    )

    referrals = models.ManyToManyField(
        "self",
        symmetrical=False,
        related_name="referred_by",
        blank=True,
    )

    def __str__(self):
        return self.name

    @cached_property
    def _connection_records(self):
        if self.pk is None:
            return []
        return list(self.connects.all())

    @cached_property
    def last_invited(self):
        invite_dates = (
            connection.invite_date
            for connection in self._connection_records
            if connection.invite_date is not None
        )
        return max(invite_dates, default=None)

    @cached_property
    def last_connected(self):
        meeting_times = (
            connection.meeting_at
            for connection in self._connection_records
            if connection.meeting_at is not None
        )
        return max(meeting_times, default=None)

    @cached_property
    def last_attended(self):
        if self.last_connected is None:
            return None
        return timezone.localtime(self.last_connected).date()

    @cached_property
    def invite_due(self):
        if self.last_invited is None:
            return None
        return _add_calendar_months(self.last_invited, 1)

    @cached_property
    def connect_due(self):
        if self.last_connected is None or self.wait is None:
            return None
        months, weeks, days = _wait_parts(self.wait)
        due_date = _add_calendar_months(
            timezone.localtime(self.last_connected, MOUNTAIN_TIME_ZONE).date(),
            months,
        )
        return due_date + timedelta(weeks=weeks, days=days)

    @cached_property
    def average_rating(self):
        ratings = [
            connection.rating
            for connection in self._connection_records
            if connection.rating is not None
        ]
        if not ratings:
            return None
        return sum(ratings) / len(ratings)

    @cached_property
    def average_rating_stars(self):
        if self.average_rating is None:
            return ""
        filled_stars = min(5, int(self.average_rating + 0.5))
        return f"{'★' * filled_stars}{'☆' * (5 - filled_stars)}"

    @cached_property
    def invite_success(self):
        if not self._connection_records:
            return None
        attended_connections = sum(
            connection.meeting_at is not None
            for connection in self._connection_records
        )
        return (attended_connections / len(self._connection_records)) * 100

    @property
    def invite(self):
        current_date = timezone.localdate()
        if self.wait is None:
            return False
        if self.invite_due is None:
            return True
        if self.connect_due is None:
            return self.invite_due <= current_date
        return (
                self.connect_due <= current_date
                and (
                        self.last_invited <= self.last_attended
                        or self.invite_due <= current_date
                )
        )


class Connect(models.Model):
    description = models.CharField(
        max_length=200,
        blank=True,
    )

    professional = models.ForeignKey(
        "Professional",
        related_name="connects",
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    recruiter = models.ForeignKey(
        "Recruiter",
        related_name="connects",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    invite_date = models.DateField(
        null=True,
        blank=True,
    )

    meeting_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    meeting_end = models.DateTimeField(null=True, blank=True)

    rating = models.IntegerField(
        null=True,
        blank=True,
        validators=[
            MinValueValidator(0),
            MaxValueValidator(5),
        ],
    )

    notes = models.TextField(blank=True)

    google_meeting_event_id = models.CharField(
        max_length=255,
        blank=True,
    )

    google_invite_event_id = models.CharField(
        max_length=255,
        blank=True,
    )

    def _prepare_meeting_interval(self):
        changed_fields = set()
        for field_name in ("meeting_at", "meeting_end"):
            value = getattr(self, field_name)
            if value is not None and timezone.is_naive(value):
                setattr(self, field_name, timezone.make_aware(value, MOUNTAIN_TIME_ZONE))
                changed_fields.add(field_name)

        if self.meeting_at is not None and self.meeting_end is None:
            self.meeting_end = self.meeting_at + timedelta(hours=1)
            changed_fields.add("meeting_end")

        return changed_fields

    def clean(self):
        self._prepare_meeting_interval()

        if self.meeting_at is None or self.meeting_end is None:
            return

        if self.meeting_end <= self.meeting_at:
            raise ValidationError(
                {"meeting_end": "Meeting end must be after the meeting start."}
            )

        conflict = (
            Connect.objects.filter(
                meeting_at__isnull=False,
                meeting_end__isnull=False,
                meeting_at__lt=self.meeting_end,
                meeting_end__gt=self.meeting_at,
            )
            .exclude(pk=self.pk)
            .order_by("meeting_at", "pk")
            .first()
        )
        if conflict is None:
            return

        conflict_start = timezone.localtime(conflict.meeting_at, MOUNTAIN_TIME_ZONE)
        conflict_end = timezone.localtime(conflict.meeting_end, MOUNTAIN_TIME_ZONE)
        start_hour = conflict_start.hour % 12 or 12
        end_hour = conflict_end.hour % 12 or 12
        start_label = (
            f"{start_hour}:{conflict_start:%M} "
            f"{'AM' if conflict_start.hour < 12 else 'PM'}"
        )
        end_label = (
            f"{end_hour}:{conflict_end:%M} "
            f"{'AM' if conflict_end.hour < 12 else 'PM'}"
        )
        raise ValidationError(
            {
                "meeting_at": (
                    f'This meeting conflicts with "{conflict}", scheduled from '
                    f"{start_label} to {end_label}."
                )
            }
        )

    def save(self, *args, **kwargs):
        changed_fields = self._prepare_meeting_interval()
        if kwargs.get("update_fields") is not None and changed_fields:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | changed_fields

        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.description or f"Connection {self.pk}"

    @property
    def notes_preview(self):
        if len(self.notes) <= 10:
            return self.notes
        return f"{self.notes[:10]}..."

    @property
    def status(self):
        now = timezone.now()

        # Meeting is scheduled for the future.
        if self.meeting_at is not None and self.meeting_at > now:
            return "Meeting Planned"

        # Meeting already happened.
        if self.meeting_at is not None:
            if self.rating is None or not self.notes.strip():
                return "Needs Review"

            return "Reviewed"

        # No meeting was scheduled from this invitation.
        if (
                (self.professional_id is not None or self.recruiter_id is not None)
                and self.invite_date is not None
        ):
            later_invitation_filters = {
                "invite_date__gt": self.invite_date,
            }
            if self.professional_id is not None:
                later_invitation_filters["professional_id"] = self.professional_id
            else:
                later_invitation_filters["recruiter_id"] = self.recruiter_id
            if Connect.objects.filter(**later_invitation_filters).exists():
                return "Invited Again"

            return "Waiting For Response"

        return None


ProfessionalConnect = Connect


class Direction(models.Model):
    connect = models.ForeignKey(
        "Connect",
        related_name="directions",
        on_delete=models.CASCADE,
    )

    description = models.TextField()

    resolved = models.BooleanField(default=False)

    def __str__(self):
        return self.description


class SearchTerm(models.Model):
    """
    The literal text entered into a job search.

    Examples:
        Data Engineer
        Python
        Django
        ETL
        Backend Developer
    """
    term = models.CharField(max_length=200, unique=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.term


class SearchPath(models.Model):
    """
    A reusable method of searching for jobs.

    Exactly one of platform/company should be populated.

    Examples:
        LinkedIn + "Data Engineer"
        Indeed + "Python"
        Acme Corp + "Backend Developer"
    """
    url = models.URLField(
        max_length=1000,
        blank=True,
    )

    platform = models.ForeignKey(
        Platform,
        on_delete=models.CASCADE,
        related_name="search_paths",
        null=True,
        blank=True,
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="search_paths",
        null=True,
        blank=True,
    )
    search_term = models.ForeignKey(
        SearchTerm,
        on_delete=models.SET_NULL,
        related_name="search_paths",
        null=True,
        blank=True,
    )

    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                        (Q(platform__isnull=False) & Q(company__isnull=True))
                        | (Q(platform__isnull=True) & Q(company__isnull=False))
                ),
                name="search_path_exactly_one_source",
            ),

            models.UniqueConstraint(
                fields=["platform", "search_term"],
                condition=Q(platform__isnull=False),
                nulls_distinct=False,
                name="unique_platform_search_path",
            ),

            models.UniqueConstraint(
                fields=["company", "search_term"],
                condition=Q(company__isnull=False),
                nulls_distinct=False,
                name="unique_company_search_path",
            ),
        ]

    @property
    def completed_observations(self):
        return self.observations.filter(
            complete=True,
        ).exclude(
            job_posting__expired=True,
        )

    @property
    def observation_count(self):
        return self.completed_observations.count()

    @property
    def success_count(self):
        return sum(
            observation.success is True
            for observation in self.completed_observations
        )

    @property
    def success_probability(self):
        return (self.success_count + 1) / (self.observation_count + 2)

    @property
    def alpha(self):
        return self.observation_count / self.success_probability

    @property
    def source_type(self):
        if self.platform_id is not None:
            return "platform"
        return "company"

    @property
    def effective_url(self):
        if self.url:
            return self.url
        if self.platform_id is not None:
            return self.platform.url
        return self.company.website

    @property
    def hide(self):
        # Inactive SearchPaths are always hidden.
        if not self.active:
            return True

        # Hide company SearchPaths when there is a recent
        # submitted application to that company.
        if self.company_id is not None:
            cutoff = timezone.now() - timedelta(days=30)

            if self.company.applications.filter(
                    submitted__gte=cutoff
            ).exists():
                return True

        last_observation = (
            SearchObservation.objects
            .filter(complete=True)
            .order_by("-created")
            .first()
        )

        # Nothing has been searched yet.
        if last_observation is None:
            return False

        return self.source_type == last_observation.search_path.source_type

    def __str__(self):
        source = self.platform or self.company
        return f'{source} — {self.search_term}'


class JobPosting(models.Model):
    """
    A job posting encountered during a search.
    """
    title = models.CharField(max_length=200)
    company_name = models.CharField(max_length=200)
    url = models.URLField(blank=True)
    description = models.TextField(blank=True)

    ai_recommend_apply = models.BooleanField(
        null=True,
        blank=True,
    )

    ai_explanation = models.TextField(
        blank=True,
    )

    apply_to = models.BooleanField(
        null=True,
        blank=True,
    )

    created = models.DateTimeField(auto_now_add=True)

    expired = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.title} — {self.company_name}"


class SearchObservation(models.Model):
    search_path = models.ForeignKey(
        SearchPath,
        on_delete=models.SET_NULL,
        related_name="observations",
        null=True,
        blank=True,
    )

    job_posting = models.ForeignKey(
        JobPosting,
        on_delete=models.SET_NULL,
        related_name="search_observations",
        null=True,
        blank=True,
    )

    complete = models.BooleanField(default=False)

    created = models.DateTimeField(auto_now_add=True)

    @property
    def success(self):
        if not self.complete:
            return None

        if self.job_posting is None:
            return False

        if self.job_posting.expired:
            return None

        if self.job_posting.apply_to is False:
            return False

        try:
            application = self.job_posting.application
        except Application.DoesNotExist:
            return True

        if application.stopped:
            return False

        if application.outcome == Application.Outcome.ACCEPTED:
            return True

        if application.outcome == Application.Outcome.REJECTED:
            return application.stage in {
                Application.Stage.ASSESSED,
                Application.Stage.INTERVIEWED,
            }

        return True

    def __str__(self):
        return f"{self.search_path} — {self.created:%Y-%m-%d}"


class Application(models.Model):
    class Outcome(models.TextChoices):
        IN_PROCESS = "in_process", "In Process"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"

    class Stage(models.IntegerChoices):
        SUBMITTED = 1, "Submitted"
        CONFIRMED = 2, "Confirmed"
        ASSESSED = 3, "Assessed"
        INTERVIEWED = 4, "Interviewed"

    job_posting = models.OneToOneField(
        "JobPosting",
        on_delete=models.CASCADE,
        related_name="application",
    )

    company = models.ForeignKey(
        "Company",
        on_delete=models.PROTECT,
        related_name="applications",
        null=True,
        blank=True,
    )

    cover_letter = models.TextField(blank=True)

    created = models.DateTimeField(auto_now_add=True)

    submitted = models.DateTimeField(
        null=True,
        blank=True,
    )

    outcome = models.CharField(
        max_length=20,
        choices=Outcome.choices,
        default=Outcome.IN_PROCESS,
    )

    stage = models.PositiveSmallIntegerField(
        choices=Stage.choices,
        default=Stage.SUBMITTED,
    )

    class StopReason(models.TextChoices):
        APPLICATION_ISSUE = "application_issue", "Application Issue"
        RECENT_APPLICATION = "recent_application", "Recently Applied to Company"
        OTHER = "other", "Other"

    stop_reason = models.CharField(
        max_length=30,
        choices=StopReason.choices,
        blank=True,
    )

    @property
    def stopped(self):
        return bool(self.stop_reason)

    def __str__(self):
        return f"Application — {self.job_posting}"


class ApplicationEmail(models.Model):
    class EmailType(models.TextChoices):
        CONFIRMATION = "confirmation", "Application Confirmation"
        ASSESSMENT = "assessment", "Online Assessment Request"
        INTERVIEW = "interview", "Interview Request"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        MY_RESPONSE = "my_response", "My Response"
        OTHER = "other", "Other"

    class Direction(models.TextChoices):
        INCOMING = "incoming", "Incoming"
        OUTGOING = "outgoing", "Outgoing"

    application = models.ForeignKey(
        "Application",
        on_delete=models.CASCADE,
        related_name="emails",
    )

    gmail_message_id = models.CharField(
        max_length=255,
        unique=True,
    )

    gmail_thread_id = models.CharField(
        max_length=255,
        blank=True,
    )

    email_type = models.CharField(
        max_length=30,
        choices=EmailType.choices,
        default=EmailType.OTHER,
    )

    direction = models.CharField(
        max_length=10,
        choices=Direction.choices,
        default=Direction.INCOMING,
    )

    subject = models.CharField(
        max_length=500,
        blank=True,
    )

    sender = models.EmailField()

    recipients = models.TextField(blank=True)

    received_at = models.DateTimeField()

    body = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        if self.email_type == self.EmailType.MY_RESPONSE:
            self.direction = self.Direction.OUTGOING
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                kwargs["update_fields"] = set(update_fields) | {"direction"}

        super().save(*args, **kwargs)


class InterviewPracticeSession(models.Model):
    class InterviewType(models.TextChoices):
        GENERAL = "general", "General Interview"
        TECHNICAL = "technical", "Technical Interview"
        BEHAVIORAL = "behavioral", "Behavioral Interview"

    application = models.ForeignKey(
        "Application",
        on_delete=models.CASCADE,
        related_name="interview_practice_sessions",
    )
    interview_type = models.CharField(
        max_length=20,
        choices=InterviewType.choices,
        default=InterviewType.GENERAL,
    )
    interview_email = models.ForeignKey(
        "ApplicationEmail",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interview_practice_sessions",
    )
    context_snapshot = models.JSONField(default=dict, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    feedback = models.TextField(blank=True)

    def clean(self):
        super().clean()
        if self.interview_email_id is None:
            return
        if self.interview_email.application_id != self.application_id:
            raise ValidationError(
                {"interview_email": "Choose an Interview Request email from this application."}
            )
        if self.interview_email.email_type != ApplicationEmail.EmailType.INTERVIEW:
            raise ValidationError(
                {"interview_email": "Choose an email classified as Interview Request."}
            )

    @property
    def completed(self):
        return self.ended_at is not None

    def __str__(self):
        return f"{self.application} — {self.get_interview_type_display()}"


class InterviewPracticeMessage(models.Model):
    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"

    session = models.ForeignKey(
        "InterviewPracticeSession",
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField()
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created", "pk"]

    def __str__(self):
        return f"{self.session} — {self.get_role_display()}"
