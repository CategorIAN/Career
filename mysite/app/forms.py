from django import forms
from django.forms import modelformset_factory

from .models import Skill


class SkillForm(forms.ModelForm):
    class Meta:
        model = Skill
        fields = ["name", "type", "rating"]


SkillFormSet = modelformset_factory(
    Skill,
    form=SkillForm,
    extra=1,
    can_delete=True,
)
