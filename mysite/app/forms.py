from django import forms
from django.forms import modelformset_factory

from .models import Skill


class SkillForm(forms.ModelForm):
    class Meta:
        model = Skill
        fields = ["name", "type", "rating", "updated"]
        widgets = {
            "updated": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date"},
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
