"""
Tracker models for slice 1: DailyLog and WeightEntry.

Single-user app — `user` is a FK to the standard Django User model. Views
always pass `request.user`; do not default the FK at the model layer (would
require runtime lookup and obscures intent).

FoodItem, MealEntry and TelegramSettings land in later slices.
"""

from django.conf import settings
from django.db import models

from . import protocol


class DailyLog(models.Model):
    """One row per user per day. Holds habit ticks and walking minutes."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="daily_logs",
    )
    date = models.DateField()

    walked_minutes = models.PositiveIntegerField(default=0)
    steps = models.PositiveIntegerField(null=True, blank=True)

    # The five habits — hardcoded per the plan doc (NWCR-backed). Do not
    # refactor into a dynamic HabitDefinition table.
    hit_protein = models.BooleanField(default=False)
    under_calories = models.BooleanField(default=False)
    walked_30 = models.BooleanField(default=False)
    ate_breakfast = models.BooleanField(default=False)
    no_alcohol_or_sugar = models.BooleanField(default=False)

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "date"], name="unique_daily_log_per_day"),
        ]
        ordering = ["-date"]

    def __str__(self) -> str:
        return f"DailyLog({self.user_id}, {self.date.isoformat()})"

    @property
    def habits_completed(self) -> int:
        """Count of the five habit booleans that are True."""
        return sum(
            1
            for field, _label in protocol.HABIT_LABELS
            if getattr(self, field)
        )

    @property
    def habits_total(self) -> int:
        """Total habits tracked (always 5; exposed for template arithmetic)."""
        return len(protocol.HABIT_LABELS)


class WeightEntry(models.Model):
    """A single weigh-in. Owner weighs weekly on Tuesday by default."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="weight_entries",
    )
    date = models.DateField()
    weight_kg = models.DecimalField(max_digits=5, decimal_places=2)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "date"], name="unique_weight_per_day"),
        ]
        ordering = ["-date"]

    def __str__(self) -> str:
        return f"WeightEntry({self.user_id}, {self.date.isoformat()}, {self.weight_kg} kg)"
