"""Meal entry model."""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class MealEntry(models.Model):
    """A logged amount of one food eaten at a point in time."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="meal_entries",
    )
    eaten_at = models.DateTimeField(default=timezone.now)
    food = models.ForeignKey(
        "tracker.FoodItem",
        on_delete=models.PROTECT,
        related_name="meal_entries",
    )
    grams = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-eaten_at"]

    def __str__(self) -> str:
        return f"MealEntry({self.user_id}, {self.food_id}, {self.grams} g)"

    def _per_100g(self, value: Decimal) -> Decimal:
        return (self.grams / Decimal("100")) * value

    @property
    def kcal(self) -> Decimal:
        """Calories for this logged quantity."""
        return self._per_100g(self.food.kcal_per_100g)

    @property
    def protein_g(self) -> Decimal:
        """Protein grams for this logged quantity."""
        return self._per_100g(self.food.protein_g)

    @property
    def fat_g(self) -> Decimal:
        """Fat grams for this logged quantity."""
        return self._per_100g(self.food.fat_g)

    @property
    def carb_g(self) -> Decimal:
        """Carbohydrate grams for this logged quantity."""
        return self._per_100g(self.food.carb_g)
