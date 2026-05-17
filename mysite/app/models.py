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

    updated = models.DateField(blank=True, null=True)

    def __str__(self):
        return f"{self.name} ({self.rating}/5)"


class Project(models.Model):
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

    def __str__(self):
        return self.title
