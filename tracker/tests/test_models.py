"""Tests for tracker models."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError

from tracker.models import DailyLog, FoodItem, MealEntry, TelegramSettings, WeightEntry


@pytest.fixture
def user(db):
    """A single user — this app is single-tenant by design."""
    user_model = get_user_model()
    return user_model.objects.create_user(username="owner", password="test-only-password")


@pytest.fixture
def food_item(db):
    """A representative food item with easy macro math."""
    return FoodItem.objects.create(
        name="Chicken breast, cooked",
        kcal_per_100g=Decimal("165.00"),
        protein_g=Decimal("31.00"),
        fat_g=Decimal("3.60"),
        carb_g=Decimal("0.00"),
        satiety_index=225,
        common_unit="100g cooked portion",
        notes="Lean protein staple",
    )


def test_daily_log_creation(user):
    """A DailyLog can be created with just user + date; all habits default False."""
    log = DailyLog.objects.create(user=user, date=date(2026, 5, 12))

    assert log.pk is not None
    assert log.walked_minutes == 0
    assert log.steps is None
    assert log.hit_protein is False
    assert log.under_calories is False
    assert log.walked_30 is False
    assert log.ate_breakfast is False
    assert log.no_alcohol_or_sugar is False
    assert log.notes == ""
    assert log.habits_completed == 0
    assert log.habits_total == 5


def test_daily_log_unique_per_day(user):
    """Two DailyLogs for the same user on the same date violate the constraint."""
    DailyLog.objects.create(user=user, date=date(2026, 5, 12))
    with pytest.raises(IntegrityError):
        DailyLog.objects.create(user=user, date=date(2026, 5, 12))


def test_habits_completed_counts_true_flags(user):
    log = DailyLog.objects.create(
        user=user,
        date=date(2026, 5, 12),
        hit_protein=True,
        walked_30=True,
        ate_breakfast=True,
    )
    assert log.habits_completed == 3


def test_weight_entry_creation(user):
    entry = WeightEntry.objects.create(
        user=user, date=date(2026, 5, 12), weight_kg=Decimal("119.40")
    )
    assert entry.pk is not None
    assert entry.weight_kg == Decimal("119.40")


def test_food_item_creation(food_item):
    assert food_item.pk is not None
    assert food_item.name == "Chicken breast, cooked"
    assert food_item.kcal_per_100g == Decimal("165.00")
    assert food_item.protein_g == Decimal("31.00")
    assert food_item.fat_g == Decimal("3.60")
    assert food_item.carb_g == Decimal("0.00")
    assert food_item.satiety_index == 225
    assert food_item.common_unit == "100g cooked portion"
    assert food_item.notes == "Lean protein staple"


@pytest.mark.parametrize(
    ("grams", "expected_kcal", "expected_protein", "expected_fat", "expected_carb"),
    [
        (
            Decimal("100.00"),
            Decimal("165.00"),
            Decimal("31.00"),
            Decimal("3.60"),
            Decimal("0.00"),
        ),
        (
            Decimal("200.00"),
            Decimal("330.00"),
            Decimal("62.00"),
            Decimal("7.20"),
            Decimal("0.00"),
        ),
        (
            Decimal("37.50"),
            Decimal("61.875"),
            Decimal("11.625"),
            Decimal("1.350"),
            Decimal("0.000"),
        ),
    ],
)
def test_meal_entry_calculates_macros(
    user,
    food_item,
    grams,
    expected_kcal,
    expected_protein,
    expected_fat,
    expected_carb,
):
    entry = MealEntry.objects.create(
        user=user,
        eaten_at=datetime(2026, 5, 12, 12, 0, tzinfo=UTC),
        food=food_item,
        grams=grams,
    )

    assert entry.kcal == expected_kcal
    assert entry.protein_g == expected_protein
    assert entry.fat_g == expected_fat
    assert entry.carb_g == expected_carb


def test_weight_entry_rejects_weight_below_minimum(user):
    entry = WeightEntry(user=user, date=date(2026, 5, 12), weight_kg=Decimal("0.00"))

    with pytest.raises(ValidationError) as exc_info:
        entry.full_clean()

    assert "weight_kg" in exc_info.value.error_dict


def test_weight_entry_rejects_weight_above_maximum(user):
    entry = WeightEntry(user=user, date=date(2026, 5, 12), weight_kg=Decimal("601.00"))

    with pytest.raises(ValidationError) as exc_info:
        entry.full_clean()

    assert "weight_kg" in exc_info.value.error_dict


def test_telegram_settings_load_creates_singleton(db):
    settings = TelegramSettings.load()

    assert settings.pk == 1
    assert settings.chat_id == ""
    assert settings.morning_ping_time.hour == 7
    assert settings.evening_ping_time.hour == 21
    assert settings.weekly_summary_day == 6
    assert settings.weekly_summary_time.hour == 19


def test_telegram_settings_save_uses_singleton_pk(db):
    settings = TelegramSettings(chat_id="123456")
    settings.save()

    assert settings.pk == 1
    assert TelegramSettings.objects.count() == 1
    assert TelegramSettings.load().chat_id == "123456"
