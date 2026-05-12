"""Food item model."""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class FoodItem(models.Model):
    """A food with per-100g macro values and optional satiety score."""

    name = models.CharField(max_length=255)
    kcal_per_100g = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(900)],
    )
    protein_g = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    fat_g = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    carb_g = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    satiety_index = models.PositiveIntegerField(null=True, blank=True)
    common_unit = models.CharField(max_length=255)
    # Default amount used when a meal-log form is submitted without an explicit
    # grams value. Nullable for foods where no single default makes sense (e.g.
    # olive oil, spices). The dashboard prefills the form input with this.
    default_grams = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    notes = models.CharField(max_length=500, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
