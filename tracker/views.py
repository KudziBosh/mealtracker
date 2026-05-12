"""Server-rendered dashboard and HTMX endpoints."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django import forms
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date

from . import protocol
from .models import DailyLog, FoodItem, MealEntry, MealTemplate, WeightEntry
from .summary import build_end_of_day_summary, build_progress_summary, meal_totals


class MealEntryForm(forms.Form):
    """Small dashboard form for logging one food and gram amount."""

    food = forms.ModelChoiceField(
        queryset=FoodItem.objects.none(),
        empty_label="Choose a food",
        widget=forms.Select(
            attrs={
                "class": (
                    "w-full rounded-md border-slate-300 text-sm shadow-sm "
                    "focus:border-emerald-500 focus:ring-emerald-500"
                ),
            }
        ),
    )
    # Grams is optional: when blank, the view falls back to the food's
    # ``default_grams`` so a user can one-tap log "1 banana" without typing.
    grams = forms.DecimalField(
        min_value=Decimal("0.01"),
        max_digits=7,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(
            attrs={
                "class": (
                    "w-full rounded-md border-slate-300 text-sm shadow-sm "
                    "focus:border-emerald-500 focus:ring-emerald-500"
                ),
                "placeholder": "grams (uses default if blank)",
                "step": "0.01",
                "inputmode": "decimal",
            }
        ),
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["food"].queryset = FoodItem.objects.order_by("name")

    def clean(self):
        """Backfill blank grams from the selected food's default_grams."""
        cleaned = super().clean()
        food = cleaned.get("food")
        grams = cleaned.get("grams")
        if food and grams in (None, ""):
            if food.default_grams is None:
                self.add_error(
                    "grams",
                    f"No default amount for {food.name}; enter a gram value.",
                )
            else:
                cleaned["grams"] = food.default_grams
        return cleaned


class LogTemplateForm(forms.Form):
    """Pick a saved recipe to fan out into N MealEntry rows."""

    meal_template = forms.ModelChoiceField(
        queryset=MealTemplate.objects.none(),
        empty_label="Choose a recipe",
        widget=forms.Select(
            attrs={
                "class": (
                    "w-full rounded-md border-slate-300 text-sm shadow-sm "
                    "focus:border-emerald-500 focus:ring-emerald-500"
                ),
            }
        ),
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["meal_template"].queryset = MealTemplate.objects.prefetch_related(
            "items"
        ).order_by("category", "name")


def _habit_rows(todays_log: DailyLog | None) -> list[dict[str, object]]:
    """Build habit button rows in the protocol-defined order."""
    return [
        {
            "field": field,
            "label": label,
            "done": bool(todays_log and getattr(todays_log, field)),
        }
        for field, label in protocol.HABIT_LABELS
    ]


def _grouped_templates() -> list[dict[str, object]]:
    """Return meal templates grouped by category, in CATEGORY_CHOICES order.

    Used to render the recipe-picker as an ``<optgroup>`` so the owner can
    skim breakfast / lunch / dinner / snack / chinese visually rather than
    one long flat list.
    """
    by_cat: dict[str, list[MealTemplate]] = {}
    for tpl in MealTemplate.objects.prefetch_related("items__food").order_by("name"):
        by_cat.setdefault(tpl.category, []).append(tpl)
    return [
        {"key": key, "label": label, "templates": by_cat.get(key, [])}
        for key, label in MealTemplate.CATEGORY_CHOICES
        if by_cat.get(key)
    ]


def _dashboard_context(
    request: HttpRequest,
    meal_form: MealEntryForm | None = None,
    template_form: LogTemplateForm | None = None,
) -> dict[str, object]:
    """Collect the dashboard state shared by full-page and partial renders."""
    today = timezone.localdate()
    week_ago = today - timedelta(days=7)

    todays_log = DailyLog.objects.filter(user=request.user, date=today).first()
    latest_weight = WeightEntry.objects.filter(user=request.user).order_by("-date").first()
    week_weights = WeightEntry.objects.filter(
        user=request.user,
        date__gte=week_ago,
    ).order_by("date")
    meals = list(
        MealEntry.objects.filter(user=request.user, eaten_at__date=today)
        .select_related("food")
        .order_by("-eaten_at")
    )

    totals = meal_totals(meals)

    return {
        "today": today,
        "todays_log": todays_log,
        "latest_weight": latest_weight,
        "week_weights": week_weights,
        "habit_rows": _habit_rows(todays_log),
        "meals": meals,
        "meal_form": meal_form or MealEntryForm(),
        "template_form": template_form or LogTemplateForm(),
        "grouped_templates": _grouped_templates(),
        "meal_totals": totals,
        "end_of_day_summary": build_end_of_day_summary(
            summary_date=today,
            daily_log=todays_log,
            totals=totals,
            latest_weight=latest_weight,
        ),
        "kcal_target": protocol.DAILY_KCAL_TARGET,
        "protein_target_g": protocol.DAILY_PROTEIN_G,
        "fat_target_g": protocol.DAILY_FAT_G,
        "carb_target_g": protocol.DAILY_CARB_G,
        "goal_weight_kg": protocol.GOAL_WEIGHT_KG,
    }


@login_required(login_url="/admin/login/")
def dashboard(request: HttpRequest) -> HttpResponse:
    """Render today's meals, habits, latest weight, and week's weigh-ins."""
    return render(request, "tracker/dashboard.html", _dashboard_context(request))


@login_required(login_url="/admin/login/")
def log_meal(request: HttpRequest) -> HttpResponse:
    """Create a meal entry from the HTMX dashboard form."""
    if request.method != "POST":
        raise Http404

    form = MealEntryForm(request.POST)
    if form.is_valid():
        MealEntry.objects.create(
            user=request.user,
            food=form.cleaned_data["food"],
            grams=form.cleaned_data["grams"],
        )
        form = MealEntryForm()

    return render(
        request,
        "tracker/partials/meals_panel.html",
        _dashboard_context(request, meal_form=form),
    )


@login_required(login_url="/admin/login/")
def log_template(request: HttpRequest) -> HttpResponse:
    """Fan a ``MealTemplate`` out into one ``MealEntry`` per ingredient row.

    All entries share the same ``eaten_at`` so the dashboard's per-meal list
    keeps them grouped. The whole insert is wrapped in a transaction so a
    bad ingredient mid-recipe rolls back cleanly.
    """
    if request.method != "POST":
        raise Http404

    form = LogTemplateForm(request.POST)
    if form.is_valid():
        template: MealTemplate = form.cleaned_data["meal_template"]
        now = timezone.now()
        with transaction.atomic():
            for item in template.items.select_related("food").all():
                MealEntry.objects.create(
                    user=request.user,
                    food=item.food,
                    grams=item.grams,
                    eaten_at=now,
                )
        form = LogTemplateForm()

    return render(
        request,
        "tracker/partials/meals_panel.html",
        _dashboard_context(request, template_form=form),
    )


@login_required(login_url="/admin/login/")
def food_default(request: HttpRequest, food_id: int) -> HttpResponse:
    """Return JSON ``{default_grams: "..."}`` for a single food.

    Tiny endpoint the dashboard's grams input hits over HTMX/JS when the user
    changes the food select — so we prefill the grams field rather than make
    them type 200 every time they log a banana.
    """
    food = FoodItem.objects.filter(pk=food_id).first()
    if food is None:
        raise Http404
    return JsonResponse(
        {
            "id": food.id,
            "name": food.name,
            "default_grams": str(food.default_grams) if food.default_grams is not None else None,
            "common_unit": food.common_unit,
        }
    )


@login_required(login_url="/admin/login/")
def progress_summary(request: HttpRequest, on_date: str | None = None) -> HttpResponse:
    """Render the comprehensive end-of-day review for ``on_date`` (or today).

    The ``on_date`` segment is optional so ``/summary/`` always lands on today;
    historical days reachable via the prev/next links in the template.
    """
    today = timezone.localdate()
    if on_date is None:
        target = today
    else:
        parsed = parse_date(on_date)
        if parsed is None:
            raise Http404("Bad date in URL — use YYYY-MM-DD.")
        target = parsed

    summary = build_progress_summary(request.user, target)
    context = {
        "summary": summary,
        "today": today,
        "is_today": target == today,
        "prev_date": target - timedelta(days=1),
        "next_date": target + timedelta(days=1) if target < today else None,
    }
    return render(request, "tracker/summary.html", context)


@login_required(login_url="/admin/login/")
def toggle_habit(request: HttpRequest, field: str) -> HttpResponse:
    """Toggle one of today's hardcoded habit booleans from the HTMX dashboard."""
    if request.method != "POST":
        raise Http404
    if field not in {habit_field for habit_field, _label in protocol.HABIT_LABELS}:
        raise Http404

    todays_log, _created = DailyLog.objects.get_or_create(
        user=request.user,
        date=timezone.localdate(),
    )
    setattr(todays_log, field, not getattr(todays_log, field))
    todays_log.save(update_fields=[field, "updated_at"])

    return render(
        request,
        "tracker/partials/habits_panel.html",
        _dashboard_context(request),
    )
