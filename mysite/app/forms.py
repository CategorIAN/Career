from datetime import timedelta

from django import forms
from django.core.exceptions import ValidationError
from django.forms import modelformset_factory
from django.utils.dateparse import parse_duration

from .models import Feature, Platform, PlatformSkill, Skill


class SkillForm(forms.ModelForm):
    class Meta:
        model = Skill
        fields = ["name", "type", "rating", "resume_ready", "updated"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "style": "width: 12rem;",
                },
            ),
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
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise ValidationError("Invalid Name")
        return name

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


class DurationWidget(forms.MultiWidget):
    template_name = "app/widgets/duration_widget.html"

    def __init__(self, attrs=None):
        widget_attrs = {
            "min": 0,
            "style": "width: 3.25rem;",
        }
        widgets = [
            forms.NumberInput(attrs={**widget_attrs, "placeholder": "Months"}),
            forms.NumberInput(attrs={**widget_attrs, "placeholder": "Weeks"}),
            forms.NumberInput(attrs={**widget_attrs, "placeholder": "Days"}),
        ]
        super().__init__(widgets, attrs)

    def decompress(self, value):
        if not value:
            return [None, None, None]
        if isinstance(value, str):
            value = parse_duration(value)
        if value is None:
            return [None, None, None]

        total_days = int(value.total_seconds()) // 86400
        months = total_days // 30
        remaining_days = total_days % 30
        weeks = remaining_days // 7
        days = remaining_days % 7
        return [months, weeks, days]


class DurationFormField(forms.MultiValueField):
    widget = DurationWidget

    def __init__(self, *args, **kwargs):
        fields = [
            forms.IntegerField(min_value=0, required=False),
            forms.IntegerField(min_value=0, required=False),
            forms.IntegerField(min_value=0, required=False),
        ]
        super().__init__(fields=fields, require_all_fields=False, *args, **kwargs)

    def compress(self, data_list):
        if not data_list or all(value in (None, "") for value in data_list):
            return None

        months, weeks, days = [int(value or 0) for value in data_list]
        return timedelta(days=(months * 30) + (weeks * 7) + days)


class FeatureForm(forms.ModelForm):
    wait = DurationFormField(required=False)

    class Meta:
        model = Feature
        fields = ["name", "wait", "updated"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "style": "width: 10rem;",
                },
            ),
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


FeatureFormSet = modelformset_factory(
    Feature,
    form=FeatureForm,
    extra=0,
    can_delete=False,
)
