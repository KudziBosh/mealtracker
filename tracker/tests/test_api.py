"""Focused tests for the minimal tracker API."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from tracker.models import DailyLog, FoodItem, WeightEntry


@pytest.fixture
def user(db):
    """A single owner account for API tests."""
    user_model = get_user_model()
    return user_model.objects.create_user(username="owner", password="test-only-password")


@pytest.fixture
def api_client(user):
    """Authenticated API client using the admin/session-auth path."""
    client = APIClient()
    client.force_login(user)
    return client


@pytest.fixture
def food_item(db):
    """Food item with easy macro math."""
    return FoodItem.objects.create(
        name="Chicken breast, cooked",
        kcal_per_100g=Decimal("165.00"),
        protein_g=Decimal("31.00"),
        fat_g=Decimal("3.60"),
        carb_g=Decimal("0.00"),
        satiety_index=225,
        common_unit="100g cooked portion",
    )


def test_api_requires_login():
    response = APIClient().get("/api/today/")

    assert response.status_code == 403


def test_post_meal_and_today_totals(api_client, food_item):
    meal_response = api_client.post(
        "/api/meals/",
        {"food_id": food_item.id, "grams": "200.00"},
        format="json",
    )

    assert meal_response.status_code == 201
    assert meal_response.data["kcal"] == "330.00"
    assert meal_response.data["protein_g"] == "62.00"

    today_response = api_client.get("/api/today/")

    assert today_response.status_code == 200
    assert today_response.data["totals"]["kcal"] == "330.00"
    assert today_response.data["totals"]["protein_g"] == "62.00"
    assert today_response.data["end_of_day_summary"]["headline"] == "Needs attention before bed"
    assert len(today_response.data["meals"]) == 1


def test_patch_daily_log_updates_allowed_fields(api_client, user):
    log_date = timezone.localdate()

    response = api_client.patch(
        f"/api/daily/{log_date.isoformat()}/",
        {"toggle": "hit_protein", "walked_minutes": 35, "steps": 4200},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["hit_protein"] is True
    assert response.data["walked_minutes"] == 35
    assert response.data["steps"] == 4200
    assert DailyLog.objects.get(user=user, date=log_date).habits_completed == 1


def test_foods_endpoint_filters_by_name(api_client):
    unique_food = FoodItem.objects.create(
        name="Test-only seitan",
        kcal_per_100g=Decimal("120.00"),
        protein_g=Decimal("24.00"),
        fat_g=Decimal("2.00"),
        carb_g=Decimal("4.00"),
        common_unit="100g test portion",
    )
    FoodItem.objects.create(
        name="Brown rice, cooked",
        kcal_per_100g=Decimal("123.00"),
        protein_g=Decimal("2.70"),
        fat_g=Decimal("1.00"),
        carb_g=Decimal("25.60"),
        common_unit="1 cup cooked",
    )

    response = api_client.get("/api/foods/?name=seitan")

    assert response.status_code == 200
    assert [item["name"] for item in response.data] == [unique_food.name]


def test_post_weight_entry(api_client):
    today = timezone.localdate().isoformat()

    response = api_client.post(
        "/api/weight/",
        {"date": today, "weight_kg": "119.40"},
        format="json",
    )

    assert response.status_code == 201
    assert response.data["date"] == today
    assert response.data["weight_kg"] == "119.40"


def test_week_summary(api_client, user):
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    DailyLog.objects.create(
        user=user,
        date=week_start,
        walked_minutes=30,
        hit_protein=True,
        under_calories=True,
    )
    DailyLog.objects.create(user=user, date=week_start + timedelta(days=1), walked_minutes=45)
    WeightEntry.objects.create(user=user, date=week_start, weight_kg=Decimal("120.00"))
    WeightEntry.objects.create(
        user=user,
        date=week_start + timedelta(days=1),
        weight_kg=Decimal("119.00"),
    )

    response = api_client.get("/api/summary/week/")

    assert response.status_code == 200
    assert response.data["week_start"] == week_start
    assert response.data["habits"]["hit"] == 2
    assert response.data["habits"]["possible"] == 35
    assert response.data["walking"]["total_min"] == 75
    assert response.data["walking"]["days_walked"] == 2
    assert response.data["weight"]["delta_kg"] == Decimal("-1.00")
