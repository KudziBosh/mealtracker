"""Tests for the meal-template + default-grams slice."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from tracker.models import FoodItem, MealEntry, MealTemplate, MealTemplateItem


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="owner", password="test-only-password")


@pytest.fixture
def client(user):
    test_client = Client()
    test_client.force_login(user)
    return test_client


@pytest.fixture
def chicken(db):
    return FoodItem.objects.create(
        name="Chicken breast (test)",
        kcal_per_100g=Decimal("165.00"),
        protein_g=Decimal("31.00"),
        fat_g=Decimal("3.60"),
        carb_g=Decimal("0.00"),
        satiety_index=210,
        common_unit="1 cooked breast = 170g",
        default_grams=Decimal("170.00"),
    )


@pytest.fixture
def potato(db):
    return FoodItem.objects.create(
        name="Potato (test)",
        kcal_per_100g=Decimal("87.00"),
        protein_g=Decimal("1.90"),
        fat_g=Decimal("0.10"),
        carb_g=Decimal("20.10"),
        satiety_index=323,
        common_unit="1 medium = 200g",
        default_grams=Decimal("200.00"),
    )


@pytest.fixture
def no_default_food(db):
    """A food whose default is intentionally NULL (oils, spices, …)."""
    return FoodItem.objects.create(
        name="Olive oil (test)",
        kcal_per_100g=Decimal("884.00"),
        protein_g=Decimal("0.00"),
        fat_g=Decimal("100.00"),
        carb_g=Decimal("0.00"),
        common_unit="1 tablespoon = 14g",
        default_grams=None,
    )


# ---- Migration 0006 (regex backfill) ----------------------------------


def test_default_grams_seeded_from_common_unit(db):
    """The data migration filled default_grams for every standard seed item."""
    sample = FoodItem.objects.get(name="Regular potato, boiled")
    assert sample.default_grams == Decimal("170.00")
    banana = FoodItem.objects.get(name="Banana, raw")
    assert banana.default_grams == Decimal("118.00")
    # Every seeded food should have a default — the regex matches all current
    # common_unit strings.
    assert FoodItem.objects.filter(default_grams__isnull=True).count() == 0


# ---- Recipe seed sanity -----------------------------------------------


def test_recipes_seeded_with_ingredients(db):
    """The recipe seed populated 25+ named recipes across categories."""
    assert MealTemplate.objects.count() >= 25
    bowl = MealTemplate.objects.get(name="Greek Yoghurt Power Bowl")
    assert bowl.category == "breakfast"
    items = list(bowl.items.values_list("food__name", "grams"))
    food_names = {name for name, _grams in items}
    assert "Greek yoghurt, plain full-fat" in food_names
    assert "Peanut butter" in food_names
    assert "Banana, raw" in food_names


def test_meal_template_items_unique_per_food(db, chicken):
    """The uniqueness constraint stops duplicate ingredient rows on a recipe."""
    template = MealTemplate.objects.create(name="Test Plate", category="other")
    MealTemplateItem.objects.create(meal_template=template, food=chicken, grams=Decimal("200"))
    with pytest.raises(Exception):
        MealTemplateItem.objects.create(meal_template=template, food=chicken, grams=Decimal("100"))


# ---- /htmx/meals/template/ (log a recipe) -----------------------------


def test_log_template_creates_one_meal_entry_per_item(client, user, chicken, potato):
    template = MealTemplate.objects.create(name="Test plate", category="lunch")
    MealTemplateItem.objects.create(meal_template=template, food=chicken, grams=Decimal("200"))
    MealTemplateItem.objects.create(meal_template=template, food=potato, grams=Decimal("150"))

    response = client.post(
        "/htmx/meals/template/",
        {"meal_template": template.id},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    entries = MealEntry.objects.filter(user=user).order_by("food__name")
    assert entries.count() == 2
    assert entries.filter(food=chicken, grams=Decimal("200.00")).exists()
    assert entries.filter(food=potato, grams=Decimal("150.00")).exists()


def test_log_template_groups_by_eaten_at(client, user, chicken, potato):
    """All entries from one recipe share the same eaten_at timestamp."""
    template = MealTemplate.objects.create(name="Group plate", category="lunch")
    MealTemplateItem.objects.create(meal_template=template, food=chicken, grams=Decimal("200"))
    MealTemplateItem.objects.create(meal_template=template, food=potato, grams=Decimal("150"))

    client.post(
        "/htmx/meals/template/",
        {"meal_template": template.id},
        HTTP_HX_REQUEST="true",
    )

    timestamps = {m.eaten_at for m in MealEntry.objects.filter(user=user)}
    assert len(timestamps) == 1


def test_log_template_requires_login():
    response = Client().post(
        "/htmx/meals/template/", {"meal_template": 1}, HTTP_HX_REQUEST="true"
    )
    # Decorator redirects to admin login.
    assert response.status_code == 302


# ---- /htmx/foods/<id>/default/ (HTMX prefill JSON) --------------------


def test_food_default_returns_default_grams(client, potato):
    response = client.get(f"/htmx/foods/{potato.id}/default/")
    assert response.status_code == 200
    body = response.json()
    assert body["default_grams"] == "200.00"
    assert body["name"] == potato.name


def test_food_default_returns_null_when_none(client, no_default_food):
    response = client.get(f"/htmx/foods/{no_default_food.id}/default/")
    assert response.status_code == 200
    assert response.json()["default_grams"] is None


def test_food_default_404_for_missing(client):
    response = client.get("/htmx/foods/999999/default/")
    assert response.status_code == 404


# ---- Single-food form: grams omitted falls back to default_grams ------


def test_log_meal_uses_default_grams_when_blank(client, user, chicken):
    response = client.post(
        "/htmx/meals/",
        {"food": chicken.id, "grams": ""},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    entry = MealEntry.objects.get(user=user)
    assert entry.grams == Decimal("170.00")  # chicken.default_grams


def test_log_meal_rejects_blank_when_no_default(client, user, no_default_food):
    response = client.post(
        "/htmx/meals/",
        {"food": no_default_food.id, "grams": ""},
        HTTP_HX_REQUEST="true",
    )
    # Re-renders the panel with a field error; no MealEntry created.
    assert response.status_code == 200
    assert MealEntry.objects.filter(user=user).count() == 0
    assert b"No default amount" in response.content


def test_log_meal_honors_explicit_grams(client, user, chicken):
    response = client.post(
        "/htmx/meals/",
        {"food": chicken.id, "grams": "250.00"},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    entry = MealEntry.objects.get(user=user)
    assert entry.grams == Decimal("250.00")
