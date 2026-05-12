"""Function-based DRF views for the minimal single-user API."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from tracker.models import DailyLog, FoodItem, MealEntry, WeightEntry
from tracker.serializers import (
    DailyLogSerializer,
    DailyLogUpdateSerializer,
    FoodItemSerializer,
    MealEntrySerializer,
    WeightEntrySerializer,
)
from tracker.summary import build_end_of_day_summary, meal_totals


def _api_decimal(value: Decimal) -> str:
    """Return a stable two-decimal string for macro totals."""
    return str(value.quantize(Decimal("0.01")))


def _api_totals(totals: dict[str, Decimal]) -> dict[str, str]:
    """Serialize macro totals as stable strings."""
    return {key: _api_decimal(value) for key, value in totals.items()}


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def today(request: Request) -> Response:
    """Return today's log, meal entries, and running macro totals."""
    today_date = timezone.localdate()
    daily_log, _created = DailyLog.objects.get_or_create(user=request.user, date=today_date)
    meals = list(
        MealEntry.objects.filter(user=request.user, eaten_at__date=today_date).select_related(
            "food"
        )
    )
    totals = meal_totals(meals)
    latest_weight = WeightEntry.objects.filter(user=request.user).order_by("-date").first()

    return Response(
        {
            "date": today_date,
            "daily_log": DailyLogSerializer(daily_log).data,
            "meals": MealEntrySerializer(meals, many=True).data,
            "totals": _api_totals(totals),
            "end_of_day_summary": build_end_of_day_summary(
                summary_date=today_date,
                daily_log=daily_log,
                totals=totals,
                latest_weight=latest_weight,
            ),
        }
    )


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def meals(request: Request) -> Response:
    """Log one food and gram amount for the authenticated owner."""
    serializer = MealEntrySerializer(data=request.data, context={"request": request})
    serializer.is_valid(raise_exception=True)
    meal = serializer.save()
    return Response(MealEntrySerializer(meal).data, status=status.HTTP_201_CREATED)


@api_view(["PATCH"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def daily_log(request: Request, log_date: str) -> Response:
    """Safely update walking fields and hardcoded habit booleans for one day."""
    parsed_date = parse_date(log_date)
    if parsed_date is None:
        return Response(
            {"detail": "Use an ISO date in YYYY-MM-DD format."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = DailyLogUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    log, _created = DailyLog.objects.get_or_create(user=request.user, date=parsed_date)
    updates = dict(serializer.validated_data)
    toggle_field = updates.pop("toggle", None)
    changed_fields = list(updates.keys())

    if toggle_field is not None:
        setattr(log, toggle_field, not getattr(log, toggle_field))
        changed_fields.append(toggle_field)

    for field, value in updates.items():
        setattr(log, field, value)
    log.save(update_fields=[*changed_fields, "updated_at"])

    return Response(DailyLogSerializer(log).data)


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def weight(request: Request) -> Response:
    """Log one weigh-in for the authenticated owner."""
    serializer = WeightEntrySerializer(data=request.data, context={"request": request})
    serializer.is_valid(raise_exception=True)
    try:
        entry = serializer.save()
    except IntegrityError:
        return Response(
            {"detail": "A weight entry already exists for this date."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return Response(WeightEntrySerializer(entry).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def week_summary(request: Request) -> Response:
    """Return the current Monday-Sunday summary used by the future Telegram bot."""
    today_date = timezone.localdate()
    week_start = today_date - timedelta(days=today_date.weekday())
    week_end = week_start + timedelta(days=6)

    logs = list(
        DailyLog.objects.filter(user=request.user, date__range=(week_start, week_end)).order_by(
            "date"
        )
    )
    weights = list(
        WeightEntry.objects.filter(user=request.user, date__range=(week_start, week_end)).order_by(
            "date"
        )
    )

    habits_hit = sum(log.habits_completed for log in logs)
    habits_possible = 7 * 5
    walking_minutes = sum(log.walked_minutes for log in logs)
    days_walked = sum(1 for log in logs if log.walked_minutes > 0)
    start_weight = weights[0].weight_kg if weights else None
    end_weight = weights[-1].weight_kg if weights else None
    delta_weight = (
        end_weight - start_weight if start_weight is not None and end_weight is not None else None
    )

    return Response(
        {
            "week_start": week_start,
            "week_end": week_end,
            "habits": {
                "hit": habits_hit,
                "possible": habits_possible,
                "pct": round((habits_hit / habits_possible) * 100),
            },
            "walking": {
                "total_min": walking_minutes,
                "days_walked": days_walked,
                "days_possible": 7,
            },
            "weight": {
                "start_kg": start_weight,
                "end_kg": end_weight,
                "delta_kg": delta_weight,
            },
            "nudge_line": "",
        }
    )


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def foods(request: Request) -> Response:
    """List foods, optionally filtering by case-insensitive name substring."""
    queryset = FoodItem.objects.all()
    name = request.query_params.get("name")
    if name:
        queryset = queryset.filter(name__icontains=name)
    return Response(FoodItemSerializer(queryset, many=True).data)
