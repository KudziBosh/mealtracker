"""Telegram settings singleton model."""

from datetime import time

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class TelegramSettings(models.Model):
    """Single-row Telegram notification settings for the owner."""

    chat_id = models.CharField(max_length=255, blank=True)
    morning_ping_time = models.TimeField(default=time(7, 0))
    evening_ping_time = models.TimeField(default=time(21, 0))
    weekly_summary_day = models.PositiveSmallIntegerField(
        default=6,
        validators=[MinValueValidator(0), MaxValueValidator(6)],
        help_text="0=Monday, 6=Sunday.",
    )
    weekly_summary_time = models.TimeField(default=time(19, 0))

    class Meta:
        verbose_name = "Telegram settings"
        verbose_name_plural = "Telegram settings"

    def __str__(self) -> str:
        return "Telegram settings"

    @classmethod
    def load(cls) -> "TelegramSettings":
        """Return the singleton row, creating it with defaults if needed."""
        settings, _created = cls.objects.get_or_create(pk=1)
        return settings

    def save(self, *args: object, **kwargs: object) -> None:
        """Always persist settings as the single row."""
        self.pk = 1
        super().save(*args, **kwargs)
