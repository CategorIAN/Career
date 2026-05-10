from django.shortcuts import redirect, render

from .forms import SkillFormSet
from .models import Skill


def skill_formset_view(request):
    if request.method == "POST":
        formset = SkillFormSet(request.POST, queryset=Skill.objects.all())
        if formset.is_valid():
            formset.save()
            return redirect("skill-formset")
    else:
        formset = SkillFormSet(queryset=Skill.objects.all())

    return render(request, "app/skill_formset.html", {"formset": formset})
