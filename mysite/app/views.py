from django.shortcuts import redirect, render
from django.core.paginator import Paginator
from django.db.models import F

from .forms import SkillForm, SkillFormSet
from .models import Skill


def skill_formset_view(request):
    page_number = request.POST.get("page") or request.GET.get("page") or 1
    queryset = Skill.objects.all().order_by(
        F("updated").asc(nulls_first=True),
        "name",
    )
    paginator = Paginator(queryset, 8)
    page_obj = paginator.get_page(page_number)
    page_queryset = page_obj.object_list

    if request.method == "POST":
        new_form = SkillForm(request.POST, prefix="new")
        formset = SkillFormSet(request.POST, queryset=page_queryset)
        new_form_has_data = new_form.has_changed()
        is_new_form_valid = new_form.is_valid() if new_form_has_data else True
        is_formset_valid = formset.is_valid()

        if is_new_form_valid and new_form_has_data:
            new_form.save()

        if is_formset_valid and is_new_form_valid:
            formset.save()
            return redirect(f"{request.path}?page={page_obj.number}")
    else:
        new_form = SkillForm(prefix="new")
        formset = SkillFormSet(queryset=page_queryset)

    return render(
        request,
        "app/skill_formset.html",
        {
            "new_form": new_form,
            "formset": formset,
            "page_obj": page_obj,
        },
    )


def blank_page_view(request):
    return render(request, "app/blank_page.html")
