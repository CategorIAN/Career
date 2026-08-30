from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class Skill(models.Model):

    name = models.CharField(max_length=100)

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
    skills = models.ManyToManyField("Skill", blank=True)
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

    skills = models.ManyToManyField(
        "Skill",
        blank=True,
        related_name="project_tasks",
    )


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






