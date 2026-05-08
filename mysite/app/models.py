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

    def __str__(self):
        return f"{self.name} ({self.rating}/5)"


