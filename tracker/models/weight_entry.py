"""Weight entry model."""

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from tracker import protocol


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
        # Bounds shared with CloseoutWeightForm via protocol.py — see comment
        # on ``WEIGHT_KG_MIN/MAX`` there for the rationale.
        validators=[
            MinValueValidator(protocol.WEIGHT_KG_MIN),
            MaxValueValidator(protocol.WEIGHT_KG_MAX),
        ],
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
