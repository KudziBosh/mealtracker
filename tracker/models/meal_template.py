"""Reusable named recipes the owner can one-tap log.

A ``MealTemplate`` ("Greek Yoghurt Power Bowl") owns one or more
``MealTemplateItem`` rows that pair a ``FoodItem`` with a gram amount. Logging
the template fans out into N ``MealEntry`` rows at the current time — so all
the existing macro math, satiety, and end-of-day summary code keeps working
without change.

See ``tracker/migrations/0008_seed_meal_templates.py`` for the recipe-bank
seed that lands on first ``migrate``.
"""

from __future__ import annotations

from django.core.validators import MinValueValidator
from django.db import models


class MealTemplate(models.Model):
    """A named, reusable composition of foods. Owner-shared; no per-user FK."""

    CATEGORY_BREAKFAST = "breakfast"
    CATEGORY_LUNCH = "lunch"
    CATEGORY_DINNER = "dinner"
    CATEGORY_SNACK = "snack"
    CATEGORY_CHINESE = "chinese"
    CATEGORY_OTHER = "other"
    CATEGORY_CHOICES = [
        (CATEGORY_BREAKFAST, "Breakfast"),
        (CATEGORY_LUNCH, "Lunch"),
        (CATEGORY_DINNER, "Dinner"),
        (CATEGORY_SNACK, "Snack"),
        (CATEGORY_CHINESE, "Chinese-style"),
        (CATEGORY_OTHER, "Other"),
    ]

    name = models.CharField(max_length=255, unique=True)
    category = models.CharField(
        max_length=16,
        choices=CATEGORY_CHOICES,
        default=CATEGORY_OTHER,
    )
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "name"]

    def __str__(self) -> str:
        return self.name


class MealTemplateItem(models.Model):
    """One ingredient line on a meal template: food + grams."""

    meal_template = models.ForeignKey(
        MealTemplate,
        on_delete=models.CASCADE,
        related_name="items",
    )
    food = models.ForeignKey(
        "tracker.FoodItem",
        on_delete=models.PROTECT,
        related_name="template_items",
    )
    grams = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )

    class Meta:
        ordering = ["id"]
        # Two lines of "Brown rice, cooked" on the same template should be one
        # row with the grams added. Enforce uniqueness so seed reruns are safe.
        constraints = [
            models.UniqueConstraint(
                fields=["meal_template", "food"],
                name="unique_food_per_template",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.food.name} · {self.grams} g"
