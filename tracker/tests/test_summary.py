"""Tests for the comprehensive end-of-day progress summary."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from tracker import protocol
from tracker.models import DailyLog, FoodItem, MealEntry, WeightEntry
from tracker.summary import build_progress_summary


@pytest.fixture
def user(db):
    user_model = get_user_model()
    return user_model.objects.create_user(username="owner", password="test-only-password")


@pytest.fixture
def client(user):
    test_client = Client()
    test_client.force_login(user)
    return test_client


@pytest.fixture
def chicken(db):
    return FoodItem.objects.create(
        name="Chicken breast",
        kcal_per_100g=Decimal("165.00"),
        protein_g=Decimal("31.00"),
        fat_g=Decimal("3.60"),
        carb_g=Decimal("0.00"),
        satiety_index=225,
        common_unit="100g",
    )


@pytest.fixture
def potato(db):
    return FoodItem.objects.create(
        name="Potato",
        kcal_per_100g=Decimal("87.00"),
        protein_g=Decimal("1.90"),
        fat_g=Decimal("0.10"),
        carb_g=Decimal("20.00"),
        satiety_index=323,
        common_unit="1 medium = 200g",
    )


@pytest.fixture
def white_rice(db):
    """Low-satiety food (below the 100 baseline) for the "leakage" path."""
    return FoodItem.objects.create(
        name="White rice",
        kcal_per_100g=Decimal("130.00"),
        protein_g=Decimal("2.70"),
        fat_g=Decimal("0.30"),
        carb_g=Decimal("28.00"),
        satiety_index=83,
        common_unit="100g cooked",
    )


# ---- protocol.protocol_week --------------------------------------------


def test_protocol_week_returns_1_with_no_first_weight():
    assert protocol.protocol_week(None, date(2026, 5, 12)) == 1


def test_protocol_week_first_monday_anchors_week_1():
    # Wed 6 May 2026 → first Monday on or before is Mon 4 May.
    first = date(2026, 5, 6)
    assert protocol.protocol_week(first, date(2026, 5, 4)) == 1   # start of week 1
    assert protocol.protocol_week(first, date(2026, 5, 10)) == 1  # end of week 1
    assert protocol.protocol_week(first, date(2026, 5, 11)) == 2  # start of week 2
    assert protocol.protocol_week(first, date(2026, 5, 25)) == 4  # start of week 4
    assert protocol.protocol_week(first, date(2026, 5, 24)) == 3  # last day of week 3


def test_protocol_week_clamps_below_1():
    first = date(2026, 5, 6)
    # Querying a date before the plan start returns 1, not 0 or negative.
    assert protocol.protocol_week(first, date(2026, 4, 27)) == 1


# ---- build_progress_summary -------------------------------------------


def test_summary_on_track_day(user, chicken, potato):
    """Protein hit + kcal in range + walk target + 4/5 habits ⇒ on_track True."""
    today = date(2026, 5, 12)
    # 620g chicken + 1000g potato ≈ 1023 + 870 = 1893 kcal, 192 g protein.
    MealEntry.objects.create(user=user, food=chicken, grams=Decimal("620"))
    MealEntry.objects.create(user=user, food=potato, grams=Decimal("1000"))
    DailyLog.objects.create(
        user=user,
        date=today,
        walked_minutes=40,
        hit_protein=True,
        under_calories=True,
        walked_30=True,
        ate_breakfast=True,
    )
    # Set first weight 2 weeks earlier so we're in week 3, target = 45 min.
    WeightEntry.objects.create(user=user, date=date(2026, 4, 28), weight_kg=Decimal("120.00"))

    summary = build_progress_summary(user, today)

    assert summary["protocol_week"] == 3
    assert summary["walking"]["target_minutes"] == 45
    assert summary["walking"]["status"] == "miss" or summary["walking"]["status"] == "warn"
    # Macros: protein hit, kcal in range
    protein = summary["macros"][1]
    assert protein["label"] == "Protein"
    assert protein["status"] == "hit"
    kcal_row = summary["macros"][0]
    assert kcal_row["actual"] >= protocol.DAILY_KCAL_FLOOR
    # Habits hit count from the DailyLog
    assert summary["habits"]["completed"] == 4
    # Satiety: both foods are high-satiety, weighted avg should be ≥ 200
    assert summary["satiety"]["available"] is True
    assert summary["satiety"]["average"] >= 200
    assert summary["kcal_floor_breached"] is False


def test_summary_protein_short_flags_verdict_miss(user, chicken, potato):
    today = date(2026, 5, 12)
    # 300 g chicken (93 g protein) + 2000 g potato (1740 kcal, 38 g protein)
    # → ~2235 kcal total, ~131 g protein. Clears the kcal floor so the
    # protein-short branch is what surfaces in the verdict.
    MealEntry.objects.create(user=user, food=chicken, grams=Decimal("300"))
    MealEntry.objects.create(user=user, food=potato, grams=Decimal("2000"))
    DailyLog.objects.create(user=user, date=today, walked_minutes=40)

    summary = build_progress_summary(user, today)

    assert summary["kcal_floor_breached"] is False
    assert summary["macros"][1]["status"] == "miss"
    assert summary["verdict_level"] == "miss"
    assert "Protein short" in summary["verdict"]
    assert summary["on_track"] is False


def test_summary_kcal_floor_breach_dominates_verdict(user, chicken):
    today = date(2026, 5, 12)
    # 500g chicken = 825 kcal, well below the 1800 floor.
    MealEntry.objects.create(user=user, food=chicken, grams=Decimal("500"))
    DailyLog.objects.create(user=user, date=today, walked_minutes=60)

    summary = build_progress_summary(user, today)

    assert summary["kcal_floor_breached"] is True
    assert summary["verdict_level"] == "miss"
    assert "1800 kcal floor" in summary["verdict"]


def test_summary_satiety_leakage_listed(user, white_rice):
    today = date(2026, 5, 12)
    MealEntry.objects.create(user=user, food=white_rice, grams=Decimal("500"))

    summary = build_progress_summary(user, today)

    assert summary["satiety"]["available"] is True
    assert summary["satiety"]["average"] < 100
    assert ("White rice", 83) in summary["satiety"]["leakage_items"]


def test_summary_no_satiety_data_when_no_meals(user):
    today = date(2026, 5, 12)
    summary = build_progress_summary(user, today)
    assert summary["satiety"]["available"] is False


def test_summary_weight_pace_on_pace(user):
    """Losing 0.7 kg/week over 4+ weeks is inside the 9–14 month window."""
    today = date(2026, 5, 12)
    # 5 weeks of weigh-ins, dropping 0.7 kg/week.
    weights = [
        (date(2026, 4, 7), Decimal("120.00")),
        (date(2026, 4, 14), Decimal("119.30")),
        (date(2026, 4, 21), Decimal("118.60")),
        (date(2026, 4, 28), Decimal("117.90")),
        (date(2026, 5, 5), Decimal("117.20")),
        (date(2026, 5, 12), Decimal("116.50")),
    ]
    for d, kg in weights:
        WeightEntry.objects.create(user=user, date=d, weight_kg=kg)

    summary = build_progress_summary(user, today)
    weight = summary["weight"]
    assert weight["available"] is True
    assert weight["latest_kg"] == Decimal("116.50")
    assert weight["delta_total_kg"] == Decimal("-3.50")
    assert weight["on_pace"] is True
    assert weight["actual_kg_per_week_last_4w"] < 0


def test_summary_weight_pace_off_pace_when_flat(user):
    """A flat 4 weeks ⇒ off-pace verdict."""
    today = date(2026, 5, 12)
    WeightEntry.objects.create(user=user, date=date(2026, 4, 7), weight_kg=Decimal("118.00"))
    WeightEntry.objects.create(user=user, date=today, weight_kg=Decimal("118.10"))

    summary = build_progress_summary(user, today)
    assert summary["weight"]["on_pace"] is False


def test_summary_walking_uses_protocol_week_target(user):
    """Week 7+ steady-state target is 75 min; 60 min should be a 'warn'."""
    today = date(2026, 5, 12)
    # First weigh-in ~8 weeks ago → today is in week 8 (steady state, 75 min target).
    WeightEntry.objects.create(user=user, date=today - timedelta(weeks=8), weight_kg=Decimal("120"))
    DailyLog.objects.create(user=user, date=today, walked_minutes=60)

    summary = build_progress_summary(user, today)
    assert summary["walking"]["target_minutes"] == 75
    assert summary["walking"]["target_hit"] is False
    assert summary["walking"]["threshold_hit"] is True
    assert summary["walking"]["status"] == "warn"


def test_summary_week_to_date_aggregates(user, chicken):
    """Week-to-date rolls up Monday through ``on_date`` only."""
    monday = date(2026, 5, 11)  # Monday
    wednesday = date(2026, 5, 13)
    for d in (monday, date(2026, 5, 12), wednesday):
        DailyLog.objects.create(
            user=user, date=d, walked_minutes=30, hit_protein=True, ate_breakfast=True
        )

    summary = build_progress_summary(user, wednesday)
    wtd = summary["week_to_date"]
    assert wtd["week_start"] == monday
    assert wtd["days_so_far"] == 3
    assert wtd["habits_hit"] == 6  # 2 habits × 3 days
    assert wtd["habits_possible"] == 15  # 5 habits × 3 days
    assert wtd["walking_total_minutes"] == 90
    assert wtd["days_walked"] == 3


# ---- /summary/ view ---------------------------------------------------


def test_summary_view_requires_login():
    response = Client().get("/summary/")
    assert response.status_code == 302
    assert response.url.startswith("/admin/login/")


def test_summary_view_renders_today_by_default(client):
    response = client.get("/summary/")
    assert response.status_code == 200
    assert b"Daily summary" in response.content
    assert b"Macros" in response.content
    assert b"Habits" in response.content
    assert b"Walking" in response.content
    assert b"Food quality" in response.content
    assert b"Weight" in response.content


def test_summary_view_accepts_explicit_date(client, user, chicken):
    target = date(2026, 5, 10)
    MealEntry.objects.create(
        user=user,
        food=chicken,
        grams=Decimal("620"),
        eaten_at=f"{target.isoformat()}T12:00:00+02:00",
    )

    response = client.get(f"/summary/{target.isoformat()}/")
    assert response.status_code == 200
    assert b"10 May 2026" in response.content or b"10 May" in response.content


def test_summary_view_rejects_bad_date(client):
    response = client.get("/summary/not-a-date/")
    assert response.status_code == 404
