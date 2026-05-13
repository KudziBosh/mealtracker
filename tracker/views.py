"""Server-rendered dashboard and HTMX endpoints."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django import forms
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date

from . import protocol
from .closeout import closeout_habit_rows, closeout_initial, closeout_suggestions
from .models import DailyLog, FoodItem, MealEntry, MealTemplate, MealTemplateItem, WeightEntry
from .summary import build_end_of_day_summary, build_progress_summary, meal_totals


# Shared Tailwind classes for form widgets — kept here so every form in this
# module emits the same visual treatment without copy-paste drift. Mirrors the
# pattern already used inside MealEntryForm/LogTemplateForm.
_INPUT_CLASS = (
    "w-full rounded-md border-slate-300 text-sm shadow-sm "
    "focus:border-emerald-500 focus:ring-emerald-500"
)
_CHECKBOX_CLASS = (
    "h-5 w-5 mt-0.5 rounded border-slate-300 text-emerald-600 "
    "focus:ring-emerald-500"
)


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


class FoodItemForm(forms.ModelForm):
    """Create or edit foods without going through Django admin."""

    class Meta:
        model = FoodItem
        fields = [
            "name",
            "kcal_per_100g",
            "protein_g",
            "fat_g",
            "carb_g",
            "satiety_index",
            "common_unit",
            "default_grams",
            "notes",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }


class MealTemplateForm(forms.ModelForm):
    """Create or edit a named reusable recipe."""

    class Meta:
        model = MealTemplate
        fields = ["name", "category", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }


MealTemplateItemFormSet = forms.inlineformset_factory(
    MealTemplate,
    MealTemplateItem,
    fields=["food", "grams"],
    extra=3,
    can_delete=True,
)


class MealEntryGramsForm(forms.ModelForm):
    """Edit grams on an already logged meal row."""

    class Meta:
        model = MealEntry
        fields = ["grams"]


class CloseoutForm(forms.ModelForm):
    """Final evening review of the five protocol habits and walking fields."""

    class Meta:
        model = DailyLog
        fields = [
            "walked_minutes",
            "steps",
            "hit_protein",
            "under_calories",
            "walked_30",
            "ate_breakfast",
            "no_alcohol_or_sugar",
            "notes",
        ]
        # All widgets explicit so the closeout page renders consistently with
        # the rest of the app — Tailwind input class on every text-y field,
        # the project-standard checkbox treatment for the five habit toggles,
        # and inputmode hints so the phone shows a numeric keypad.
        widgets = {
            "walked_minutes": forms.NumberInput(
                attrs={"class": _INPUT_CLASS, "min": "0", "inputmode": "numeric"}
            ),
            "steps": forms.NumberInput(
                attrs={"class": _INPUT_CLASS, "min": "0", "inputmode": "numeric"}
            ),
            "hit_protein": forms.CheckboxInput(attrs={"class": _CHECKBOX_CLASS}),
            "under_calories": forms.CheckboxInput(attrs={"class": _CHECKBOX_CLASS}),
            "walked_30": forms.CheckboxInput(attrs={"class": _CHECKBOX_CLASS}),
            "ate_breakfast": forms.CheckboxInput(attrs={"class": _CHECKBOX_CLASS}),
            "no_alcohol_or_sugar": forms.CheckboxInput(attrs={"class": _CHECKBOX_CLASS}),
            "notes": forms.Textarea(attrs={"class": _INPUT_CLASS, "rows": 3}),
        }


class CloseoutWeightForm(forms.Form):
    """Optional weight capture inside the closeout ritual."""

    weight_kg = forms.DecimalField(
        max_digits=5,
        decimal_places=2,
        # Shared bounds — see ``protocol.WEIGHT_KG_MIN/MAX``. Keeping these in
        # one place means a typo on the scale can't sneak past the form just
        # because the form's bounds drifted from the model's.
        min_value=Decimal(protocol.WEIGHT_KG_MIN),
        max_value=Decimal(protocol.WEIGHT_KG_MAX),
        required=False,
        widget=forms.NumberInput(
            attrs={
                "class": _INPUT_CLASS,
                "step": "0.01",
                "inputmode": "decimal",
                "placeholder": "e.g. 119.40",
            }
        ),
    )
    weight_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": _INPUT_CLASS, "rows": 2}),
    )


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


# ---- Macro progress (dashboard cards) ------------------------------------


def _macro_progress(totals: dict[str, Decimal]) -> dict[str, dict[str, object]]:
    """Compute % / status / remaining for the dashboard macro cards.

    Mirrors the more elaborate end-of-day summary logic but stays cheap to call
    on every HTMX panel render — the dashboard wants a quick "70 % of protein"
    glance, not a full verdict. Protein is the only non-negotiable; everything
    else flags ``warn`` once you cross the target.
    """

    def _row(actual: Decimal, target: int, *, non_negotiable: bool) -> dict[str, object]:
        target_dec = Decimal(target)
        pct = int(min(actual / target_dec * 100, Decimal(200))) if target_dec else 0
        if non_negotiable:
            status = "hit" if actual >= target_dec else "miss"
        else:
            status = "warn" if actual > target_dec else "hit" if actual >= target_dec else "ok"
        return {
            "actual": actual,
            "target": target,
            "pct": pct,
            "pct_capped": min(pct, 100),
            "status": status,
            "over": max(actual - target_dec, Decimal(0)),
            "remaining": max(target_dec - actual, Decimal(0)),
        }

    return {
        "kcal": _row(totals["kcal"], protocol.DAILY_KCAL_TARGET, non_negotiable=False),
        "protein": _row(totals["protein_g"], protocol.DAILY_PROTEIN_G, non_negotiable=True),
    }


# ---- Toast / OOB helpers --------------------------------------------------


def _toast(
    message: str,
    *,
    undo_url: str | None = None,
    undo_payload: dict[str, str] | None = None,
    undo_target: str = "#meals-panel",
    kind: str = "info",
) -> dict[str, object]:
    """Shape a toast dict the OOB partial knows how to render.

    ``kind`` drives the accent colour; ``undo_*`` are optional so the same
    helper can render plain status messages later if needed. ``undo_target``
    is the CSS selector HTMX swaps when the user taps Undo — defaults to the
    meals panel since that's the most common case.
    """
    return {
        "message": message,
        "undo_url": undo_url,
        "undo_payload": undo_payload or {},
        "undo_target": undo_target,
        "kind": kind,
    }


def _htmx_panel_response(
    request: HttpRequest,
    *,
    panel_template: str,
    context: dict[str, object],
    toast: dict[str, object] | None = None,
) -> HttpResponse:
    """Render a panel partial plus an out-of-band toast region in one response.

    HTMX picks up the ``hx-swap-oob`` marker on the toast div and replaces
    ``#toast-area`` in the base template, so the dashboard panel and the toast
    update in one round-trip. Passing ``toast=None`` still emits an empty toast
    region — that's how we clear a stale toast after an undo.
    """
    panel_html = render_to_string(panel_template, context, request=request)
    toast_html = render_to_string("tracker/partials/toast.html", {"toast": toast}, request=request)
    return HttpResponse(panel_html + toast_html)


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
        "macro_progress": _macro_progress(totals),
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
    toast = None
    if form.is_valid():
        food = form.cleaned_data["food"]
        grams = form.cleaned_data["grams"]
        meal = MealEntry.objects.create(user=request.user, food=food, grams=grams)
        form = MealEntryForm()
        toast = _toast(
            message=f"Logged {grams:.0f} g {food.name} · {meal.kcal:.0f} kcal",
            undo_url=reverse("tracker:htmx-undo-meal"),
            undo_payload={"meal_id": str(meal.id)},
            kind="success",
        )

    return _htmx_panel_response(
        request,
        panel_template="tracker/partials/meals_panel.html",
        context=_dashboard_context(request, meal_form=form),
        toast=toast,
    )


@login_required(login_url="/admin/login/")
def undo_meal(request: HttpRequest) -> HttpResponse:
    """Delete a freshly logged meal and re-render the panel with a cleared toast.

    Called from the "Undo" button on the success toast. We scope the lookup to
    ``request.user`` so a stale toast can't be replayed against someone else's
    rows (single-user app today, but the constraint is cheap and future-proof).
    """
    if request.method != "POST":
        raise Http404

    meal = MealEntry.objects.filter(pk=request.POST.get("meal_id"), user=request.user).first()
    if meal is not None:
        meal.delete()

    return _htmx_panel_response(
        request,
        panel_template="tracker/partials/meals_panel.html",
        context=_dashboard_context(request),
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
    toast = None
    if form.is_valid():
        template: MealTemplate = form.cleaned_data["meal_template"]
        now = timezone.now()
        created_ids: list[int] = []
        with transaction.atomic():
            for item in template.items.select_related("food").all():
                meal = MealEntry.objects.create(
                    user=request.user,
                    food=item.food,
                    grams=item.grams,
                    eaten_at=now,
                )
                created_ids.append(meal.id)
        form = LogTemplateForm()
        if created_ids:
            toast = _toast(
                message=(
                    f"Logged {template.name} · "
                    f"{len(created_ids)} ingredient{'s' if len(created_ids) != 1 else ''}"
                ),
                undo_url=reverse("tracker:htmx-undo-template-log"),
                undo_payload={"meal_ids": ",".join(str(i) for i in created_ids)},
                kind="success",
            )

    return _htmx_panel_response(
        request,
        panel_template="tracker/partials/meals_panel.html",
        context=_dashboard_context(request, template_form=form),
        toast=toast,
    )


@login_required(login_url="/admin/login/")
def undo_template_log(request: HttpRequest) -> HttpResponse:
    """Delete every meal row from a recipe log call.

    Receives a comma-separated ``meal_ids`` string. Anything not parseable as an
    integer is dropped silently — the toast generated those IDs locally, so a
    malformed value is a client bug, not a user error.
    """
    if request.method != "POST":
        raise Http404

    raw_ids = request.POST.get("meal_ids", "")
    ids: list[int] = []
    for token in raw_ids.split(","):
        token = token.strip()
        if token.isdigit():
            ids.append(int(token))

    if ids:
        MealEntry.objects.filter(user=request.user, pk__in=ids).delete()

    return _htmx_panel_response(
        request,
        panel_template="tracker/partials/meals_panel.html",
        context=_dashboard_context(request),
    )


@login_required(login_url="/admin/login/")
def food_search(request: HttpRequest) -> HttpResponse:
    """Return a small HTMX-friendly list of foods matching ``food_search``.

    The dashboard combobox hits this on every debounced keystroke. We cap the
    result list small so the dropdown stays scannable on a phone and the
    response payload stays trivial.
    """
    query = request.GET.get("food_search", "").strip()
    queryset = FoodItem.objects.all()
    if query:
        queryset = queryset.filter(name__icontains=query)
    return render(
        request,
        "tracker/partials/food_search_results.html",
        {
            "foods": list(queryset.order_by("name")[:12]),
            "query": query,
        },
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
def closeout(request: HttpRequest) -> HttpResponse:
    """Guided evening closeout: habits, walking, notes, and optional weight."""
    today = timezone.localdate()
    daily_log = DailyLog.objects.filter(user=request.user, date=today).first()
    meals = list(
        MealEntry.objects.filter(user=request.user, eaten_at__date=today).select_related("food")
    )
    totals = meal_totals(meals)
    suggestions = closeout_suggestions(daily_log=daily_log, totals=totals)
    weight_entry = WeightEntry.objects.filter(user=request.user, date=today).first()

    if request.method == "POST":
        daily_log, _created = DailyLog.objects.get_or_create(user=request.user, date=today)
        form = CloseoutForm(request.POST, instance=daily_log)
        weight_form = CloseoutWeightForm(request.POST)
        if form.is_valid() and weight_form.is_valid():
            log = form.save(commit=False)
            # First-close-wins: subsequent edits should not move the timestamp.
            # ``closed_at`` is the *ritual* timestamp, not the last-saved one;
            # auto-updated fields (``updated_at``) already cover that purpose.
            log.closed_at = log.closed_at or timezone.now()
            log.save()

            weight_kg = weight_form.cleaned_data["weight_kg"]
            if weight_kg is not None:
                WeightEntry.objects.update_or_create(
                    user=request.user,
                    date=today,
                    defaults={
                        "weight_kg": weight_kg,
                        "notes": weight_form.cleaned_data["weight_notes"],
                    },
                )
            return redirect("tracker:summary")
    else:
        form = CloseoutForm(
            instance=daily_log,
            initial=closeout_initial(daily_log=daily_log, suggestions=suggestions),
        )
        weight_form = CloseoutWeightForm(
            initial={
                "weight_kg": weight_entry.weight_kg if weight_entry else None,
                "weight_notes": weight_entry.notes if weight_entry else "",
            }
        )

    return render(
        request,
        "tracker/closeout.html",
        {
            "today": today,
            "form": form,
            "weight_form": weight_form,
            "daily_log": daily_log,
            "weight_entry": weight_entry,
            "suggestions": suggestions,
            "habit_rows": closeout_habit_rows(
                form=form,
                suggestions=suggestions,
                has_saved_log=daily_log is not None,
            ),
            "meal_totals": totals,
            "weigh_in_due": today.weekday() == protocol.WEIGH_IN_DAY,
            "protein_target_g": protocol.DAILY_PROTEIN_G,
            "kcal_target": protocol.DAILY_KCAL_TARGET,
            "kcal_floor": protocol.DAILY_KCAL_FLOOR,
            "walking_threshold": protocol.WALKING_HABIT_THRESHOLD_MIN,
        },
    )


@login_required(login_url="/admin/login/")
def food_list(request: HttpRequest) -> HttpResponse:
    """List foods and link to add/edit pages for macro calibration."""
    query = request.GET.get("q", "").strip()
    foods = FoodItem.objects.all()
    if query:
        foods = foods.filter(name__icontains=query)

    return render(
        request,
        "tracker/foods/list.html",
        {
            "foods": foods.order_by("name"),
            "query": query,
        },
    )


@login_required(login_url="/admin/login/")
def food_create(request: HttpRequest) -> HttpResponse:
    """Add one FoodItem from the browser."""
    form = FoodItemForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        food = form.save()
        return redirect("tracker:food-edit", food_id=food.id)

    return render(request, "tracker/foods/form.html", {"form": form, "food": None})


@login_required(login_url="/admin/login/")
def food_edit(request: HttpRequest, food_id: int) -> HttpResponse:
    """Edit macros/default grams for a FoodItem, including seeded foods."""
    food = get_object_or_404(FoodItem, pk=food_id)
    form = FoodItemForm(request.POST or None, instance=food)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("tracker:foods")

    return render(request, "tracker/foods/form.html", {"form": form, "food": food})


@login_required(login_url="/admin/login/")
def recipe_list(request: HttpRequest) -> HttpResponse:
    """List saved meal templates/recipes."""
    recipes = MealTemplate.objects.prefetch_related("items__food").order_by("category", "name")
    return render(request, "tracker/recipes/list.html", {"recipes": recipes})


@login_required(login_url="/admin/login/")
def recipe_create(request: HttpRequest) -> HttpResponse:
    """Build a new recipe with ingredient rows."""
    recipe = MealTemplate()
    form = MealTemplateForm(request.POST or None, instance=recipe)
    formset = MealTemplateItemFormSet(request.POST or None, instance=recipe)
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            recipe = form.save()
            formset.instance = recipe
            formset.save()
        return redirect("tracker:recipe-edit", recipe_id=recipe.id)

    return render(
        request,
        "tracker/recipes/form.html",
        {"form": form, "formset": formset, "recipe": None},
    )


@login_required(login_url="/admin/login/")
def recipe_edit(request: HttpRequest, recipe_id: int) -> HttpResponse:
    """Edit a saved recipe and its ingredient rows."""
    recipe = get_object_or_404(MealTemplate, pk=recipe_id)
    form = MealTemplateForm(request.POST or None, instance=recipe)
    formset = MealTemplateItemFormSet(request.POST or None, instance=recipe)
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            form.save()
            formset.save()
        return redirect("tracker:recipes")

    return render(
        request,
        "tracker/recipes/form.html",
        {"form": form, "formset": formset, "recipe": recipe},
    )


@login_required(login_url="/admin/login/")
def logged_meals(request: HttpRequest) -> HttpResponse:
    """Edit/delete today's logged meal rows on a dedicated page."""
    target = timezone.localdate()

    if request.method == "POST":
        meal = get_object_or_404(MealEntry, pk=request.POST.get("meal_id"), user=request.user)
        if request.POST.get("action") == "delete":
            meal.delete()
            return redirect("tracker:logged-meals")

        form = MealEntryGramsForm(request.POST, instance=meal)
        if form.is_valid():
            form.save()
            return redirect("tracker:logged-meals")

    meals = list(
        MealEntry.objects.filter(user=request.user, eaten_at__date=target)
        .select_related("food")
        .order_by("-eaten_at", "-id")
    )
    return render(
        request,
        "tracker/meals/list.html",
        {
            "target_date": target,
            "meals": meals,
            "totals": meal_totals(meals),
        },
    )


@login_required(login_url="/admin/login/")
def toggle_habit(request: HttpRequest, field: str) -> HttpResponse:
    """Toggle one of today's hardcoded habit booleans from the HTMX dashboard.

    Suppresses the toast when an ``X-Undo`` header is set so the "undo" button
    can re-POST the same endpoint without spawning an undo-of-undo toast loop.
    """
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

    toast = None
    if request.headers.get("X-Undo") != "true":
        new_state = getattr(todays_log, field)
        label = dict(protocol.HABIT_LABELS)[field]
        toast = _toast(
            message=(f"Marked: {label}" if new_state else f"Cleared: {label}"),
            undo_url=reverse("tracker:htmx-toggle-habit", args=[field]),
            undo_target="#habits-panel",
            kind="success" if new_state else "info",
        )

    return _htmx_panel_response(
        request,
        panel_template="tracker/partials/habits_panel.html",
        context=_dashboard_context(request),
        toast=toast,
    )
