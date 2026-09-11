from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.utils.functional import cached_property
from calendar import monthrange
from datetime import timedelta
from zoneinfo import ZoneInfo


MOUNTAIN_TIME_ZONE = ZoneInfo("America/Denver")


def _add_calendar_months(date_value, months):
    if not months:
        return date_value

    total_month_index = (date_value.month - 1) + months
    year = date_value.year + (total_month_index // 12)
    month = (total_month_index % 12) + 1
    day = min(date_value.day, monthrange(year, month)[1])
    return date_value.replace(year=year, month=month, day=day)


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
        related_name="peers",
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
        return timezone.localtime(self.last_connected + self.wait).date()

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


class ProfessionalConnect(models.Model):
    description = models.CharField(
        max_length=200,
        blank=True,
    )

    person = models.ForeignKey(
        "Professional",
        related_name="connects",
        on_delete=models.SET_NULL,
        null=True,
        blank=True
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
            ProfessionalConnect.objects.filter(
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
                self.person_id is not None
                and self.invite_date is not None
        ):
            if ProfessionalConnect.objects.filter(
                    person_id=self.person_id,
                    invite_date__gt=self.invite_date,
            ).exists():
                return "Invited Again"

            return "Waiting For Response"

        return None


class Direction(models.Model):
    connect = models.ForeignKey(
        "ProfessionalConnect",
        related_name="directions",
        on_delete=models.CASCADE,
    )

    description = models.TextField()

    resolved = models.BooleanField(default=False)

    def __str__(self):
        return self.description
