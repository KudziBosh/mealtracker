"""
View layer for slice 1.

Just the dashboard for now. API views (DRF) and HTMX partials land in later
slices.
"""

from __future__ import annotations

from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from . import protocol
from .models import DailyLog, WeightEntry


@login_required(login_url="/admin/login/")
def dashboard(request: HttpRequest) -> HttpResponse:
    """Render today's log, the latest weight, and the week's weigh-ins."""
    today = date.today()
    week_ago = today - timedelta(days=7)

    todays_log = DailyLog.objects.filter(user=request.user, date=today).first()
    latest_weight = (
        WeightEntry.objects.filter(user=request.user).order_by("-date").first()
    )
    week_weights = WeightEntry.objects.filter(
        user=request.user, date__gte=week_ago
    ).order_by("date")

    # Render habit rows from the protocol order, looking up the boolean off the
    # log (if it exists) so the template doesn't branch on None.
    habit_rows = [
        {
            "field": field,
            "label": label,
            "done": bool(todays_log and getattr(todays_log, field)),
        }
        for field, label in protocol.HABIT_LABELS
    ]

    context = {
        "today": today,
        "todays_log": todays_log,
        "latest_weight": latest_weight,
        "week_weights": week_weights,
        "habit_rows": habit_rows,
        "kcal_target": protocol.DAILY_KCAL_TARGET,
        "protein_target_g": protocol.DAILY_PROTEIN_G,
        "fat_target_g": protocol.DAILY_FAT_G,
        "carb_target_g": protocol.DAILY_CARB_G,
        "goal_weight_kg": protocol.GOAL_WEIGHT_KG,
    }
    return render(request, "tracker/dashboard.html", context)
