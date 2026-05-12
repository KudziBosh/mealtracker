"""Tests for tracker models — slice 1 scope."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db.utils import IntegrityError

from tracker.models import DailyLog, WeightEntry


@pytest.fixture
def user(db):
    """A single user — this app is single-tenant by design."""
    User = get_user_model()
    return User.objects.create_user(username="owner", password="test-only-password")


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
