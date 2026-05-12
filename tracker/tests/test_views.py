"""Focused tests for the server-rendered dashboard and HTMX endpoints."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from tracker.models import DailyLog, FoodItem, MealEntry


@pytest.fixture
def user(db):
    """A single owner account for dashboard tests."""
    user_model = get_user_model()
    return user_model.objects.create_user(username="owner", password="test-only-password")


@pytest.fixture
def client(user):
    """Authenticated Django test client using the admin/session-auth path."""
    test_client = Client()
    test_client.force_login(user)
    return test_client


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


def test_dashboard_requires_login():
    response = Client().get("/")

    assert response.status_code == 302
    assert response.url.startswith("/admin/login/")


def test_htmx_log_meal_creates_entry_and_renders_totals(client, user, food_item):
    response = client.post(
        "/htmx/meals/",
        {"food": food_item.id, "grams": "200.00"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert MealEntry.objects.filter(
        user=user,
        food=food_item,
        grams=Decimal("200.00"),
    ).exists()
    assert b"330" in response.content
    assert b"62" in response.content


def test_htmx_toggle_habit_creates_today_log_and_toggles_field(client, user):
    response = client.post(
        "/htmx/habits/hit_protein/toggle/",
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    log = DailyLog.objects.get(user=user, date=timezone.localdate())
    assert log.hit_protein is True
    assert b"1/5 habits done" in response.content


def test_dashboard_shows_end_of_day_summary(client, user, food_item):
    MealEntry.objects.create(user=user, food=food_item, grams=Decimal("620.00"))
    DailyLog.objects.create(
        user=user,
        date=timezone.localdate(),
        walked_minutes=35,
        hit_protein=True,
        under_calories=True,
        walked_30=True,
        ate_breakfast=True,
    )

    response = client.get("/")

    assert response.status_code == 200
    assert b"End-of-day summary" in response.content
    assert b"On track today" in response.content
    assert b"4/5 habits done" in response.content
