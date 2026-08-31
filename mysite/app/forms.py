from django import forms
from django.forms import modelformset_factory

from .models import Platform, PlatformSkill, Skill


class SkillForm(forms.ModelForm):
    class Meta:
        model = Skill
        fields = ["name", "type", "rating", "updated"]
        widgets = {
            "updated": forms.DateInput(
                format="%Y-%m-%d",
                attrs={
                    "type": "date",
                    "autocomplete": "off",
                    "data-form-type": "other",
                },
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = False

    def clean_name(self):
        return self.cleaned_data.get("name") or ""

    def clean_rating(self):
        rating = self.cleaned_data.get("rating")
        return 0 if rating in (None, "") else rating


SkillFormSet = modelformset_factory(
    Skill,
    form=SkillForm,
    extra=0,
    can_delete=True,
)


class PlatformForm(forms.ModelForm):
    class Meta:
        model = Platform
        fields = ["name", "url", "max_skills"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = False

    def clean_name(self):
        return self.cleaned_data.get("name") or ""


PlatformFormSet = modelformset_factory(
    Platform,
    form=PlatformForm,
    extra=0,
    can_delete=True,
)


NULL_BOOLEAN_CHOICES = (
    ("", "Unknown"),
    ("true", "Yes"),
    ("false", "No"),
)


class PlatformSkillForm(forms.ModelForm):
    available = forms.TypedChoiceField(
        choices=NULL_BOOLEAN_CHOICES,
        coerce=lambda value: {
            "true": True,
            "false": False,
            "": None,
            None: None,
        }.get(value, None),
        empty_value=None,
        required=False,
    )
    listed = forms.TypedChoiceField(
        choices=NULL_BOOLEAN_CHOICES,
        coerce=lambda value: {
            "true": True,
            "false": False,
            "": None,
            None: None,
        }.get(value, None),
        empty_value=None,
        required=False,
    )

    class Meta:
        model = PlatformSkill
        fields = ["available", "listed", "updated"]
        widgets = {
            "updated": forms.DateInput(
                format="%Y-%m-%d",
                attrs={
                    "type": "date",
                    "autocomplete": "off",
                    "data-form-type": "other",
                },
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = False

        for field_name in ("available", "listed"):
            value = getattr(self.instance, field_name, None)
            self.initial[field_name] = (
                "true" if value is True else "false" if value is False else ""
            )


PlatformSkillFormSet = modelformset_factory(
    PlatformSkill,
    form=PlatformSkillForm,
    extra=0,
    can_delete=False,
)
