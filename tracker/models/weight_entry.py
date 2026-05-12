"""Weight entry model."""

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class WeightEntry(models.Model):
    """A single weigh-in. Owner weighs weekly on Tuesday by default."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="weight_entries",
    )
    date = models.DateField()
    weight_kg = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(30), MaxValueValidator(600)],
    )
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
