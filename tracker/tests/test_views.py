"""Focused tests for the server-rendered dashboard and HTMX endpoints."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from tracker.models import (
    DailyLog,
    FoodItem,
    MealEntry,
    MealTemplate,
    MealTemplateItem,
    WeightEntry,
)


@pytest.fixture
def user(db):
    """A single owner account for dashboard tests."""
    user_model = get_user_model()
    return user_model.objects.create_user(username="owner", password="test-only-password")


@pytest.fixture
def client(user):
    """Authenticated Django test client using the admin/session-auth path."""
    test_client = Client()
    test_client.force_login(user)
    return test_client


@pytest.fixture
def food_item(db):
    """Food item with easy macro math."""
    return FoodItem.objects.create(
        name="Chicken breast, cooked",
        kcal_per_100g=Decimal("165.00"),
        protein_g=Decimal("31.00"),
        fat_g=Decimal("3.60"),
        carb_g=Decimal("0.00"),
        satiety_index=225,
        common_unit="100g cooked portion",
    )


def test_dashboard_requires_login():
    response = Client().get("/")

    assert response.status_code == 302
    assert response.url.startswith("/admin/login/")


def test_htmx_log_meal_creates_entry_and_renders_totals(client, user, food_item):
    response = client.post(
        "/htmx/meals/",
        {"food": food_item.id, "grams": "200.00"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert MealEntry.objects.filter(
        user=user,
        food=food_item,
        grams=Decimal("200.00"),
    ).exists()
    assert b"330" in response.content
    assert b"62" in response.content


def test_htmx_log_meal_emits_undo_toast(client, user, food_item):
    """The success toast must carry the new meal's id so Undo can delete it."""
    response = client.post(
        "/htmx/meals/",
        {"food": food_item.id, "grams": "150.00"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    meal = MealEntry.objects.get(user=user, food=food_item)
    assert b'id="toast-area"' in response.content
    assert b"Logged" in response.content
    assert f'name="meal_id" value="{meal.id}"'.encode() in response.content
    assert b"/htmx/meals/undo/" in response.content


def test_htmx_undo_meal_deletes_just_logged_row(client, user, food_item):
    meal = MealEntry.objects.create(user=user, food=food_item, grams=Decimal("150.00"))

    response = client.post(
        "/htmx/meals/undo/",
        {"meal_id": str(meal.id)},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert not MealEntry.objects.filter(pk=meal.id).exists()
    # An empty toast region clears any previous toast in the same swap.
    assert b'id="toast-area"' in response.content
    assert b"data-toast" not in response.content


def test_htmx_undo_meal_ignores_other_users(client, food_item):
    """An undo can't reach into another user's meal — silent no-op."""
    other = get_user_model().objects.create_user(username="other", password="x")
    other_meal = MealEntry.objects.create(user=other, food=food_item, grams=Decimal("100.00"))

    response = client.post(
        "/htmx/meals/undo/",
        {"meal_id": str(other_meal.id)},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert MealEntry.objects.filter(pk=other_meal.id).exists()


def test_htmx_log_template_emits_undo_toast_with_all_ids(client, user, food_item):
    second_food = FoodItem.objects.create(
        name="Brown rice, cooked",
        kcal_per_100g=Decimal("123.00"),
        protein_g=Decimal("2.70"),
        fat_g=Decimal("1.00"),
        carb_g=Decimal("25.50"),
        satiety_index=132,
        common_unit="1 cup = 200g",
        default_grams=Decimal("200.00"),
    )
    recipe = MealTemplate.objects.create(
        name="Test combo plate",
        category=MealTemplate.CATEGORY_LUNCH,
    )
    MealTemplateItem.objects.create(meal_template=recipe, food=food_item, grams=Decimal("100.00"))
    MealTemplateItem.objects.create(meal_template=recipe, food=second_food, grams=Decimal("200.00"))

    response = client.post(
        "/htmx/meals/template/",
        {"meal_template": recipe.id},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    meals = MealEntry.objects.filter(user=user).order_by("id")
    assert meals.count() == 2
    expected_ids = ",".join(str(m.id) for m in meals)
    assert f'value="{expected_ids}"'.encode() in response.content
    assert b"/htmx/meals/template/undo/" in response.content


def test_htmx_undo_template_log_deletes_all_listed_meals(client, user, food_item):
    a = MealEntry.objects.create(user=user, food=food_item, grams=Decimal("100.00"))
    b = MealEntry.objects.create(user=user, food=food_item, grams=Decimal("50.00"))

    response = client.post(
        "/htmx/meals/template/undo/",
        {"meal_ids": f"{a.id},{b.id},not-a-number"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert MealEntry.objects.filter(user=user).count() == 0


def test_htmx_toggle_habit_creates_today_log_and_toggles_field(client, user):
    response = client.post(
        "/htmx/habits/hit_protein/toggle/",
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    log = DailyLog.objects.get(user=user, date=timezone.localdate())
    assert log.hit_protein is True
    assert b"1/5 habits done" in response.content


def test_htmx_toggle_habit_emits_undo_toast_then_undo_suppresses_it(client, user):
    """First tap shows the undo toast; the undo POST sets X-Undo so no new toast."""
    first = client.post(
        "/htmx/habits/walked_30/toggle/",
        HTTP_HX_REQUEST="true",
    )
    assert first.status_code == 200
    assert b"data-toast" in first.content
    assert b"Marked: Walked 30+ minutes" in first.content

    second = client.post(
        "/htmx/habits/walked_30/toggle/",
        HTTP_HX_REQUEST="true",
        HTTP_X_UNDO="true",
    )
    assert second.status_code == 200
    log = DailyLog.objects.get(user=user, date=timezone.localdate())
    assert log.walked_30 is False
    # The undo response still includes the toast wrapper (OOB clears stale toast)
    # but no actual toast body.
    assert b'id="toast-area"' in second.content
    assert b"data-toast" not in second.content


def test_htmx_food_search_filters_by_name(client, food_item):
    FoodItem.objects.create(
        name="Banana",
        kcal_per_100g=Decimal("89.00"),
        protein_g=Decimal("1.10"),
        fat_g=Decimal("0.30"),
        carb_g=Decimal("23.00"),
        satiety_index=118,
        common_unit="1 medium = 120g",
        default_grams=Decimal("120.00"),
    )

    matching = client.get("/htmx/foods/search/", {"food_search": "chick"})
    assert matching.status_code == 200
    assert food_item.name.encode() in matching.content
    assert b"Banana" not in matching.content

    empty = client.get("/htmx/foods/search/", {"food_search": "no-such-thing"})
    assert empty.status_code == 200
    assert b"No foods match" in empty.content


def test_dashboard_shows_end_of_day_summary(client, user, food_item):
    MealEntry.objects.create(user=user, food=food_item, grams=Decimal("620.00"))
    DailyLog.objects.create(
        user=user,
        date=timezone.localdate(),
        walked_minutes=35,
        hit_protein=True,
        under_calories=True,
        walked_30=True,
        ate_breakfast=True,
    )

    response = client.get("/")

    assert response.status_code == 200
    assert b"End-of-day summary" in response.content
    assert b"On track today" in response.content
    assert b"4/5 habits done" in response.content


def test_closeout_prefills_suggestions_when_no_saved_log(client, user, food_item):
    MealEntry.objects.create(user=user, food=food_item, grams=Decimal("620.00"))

    response = client.get("/closeout/")

    assert response.status_code == 200
    assert response.context["suggestions"]["hit_protein"] is True
    assert response.context["form"].initial["hit_protein"] is True
    assert b"Daily closeout" in response.content


def test_closeout_preserves_existing_manual_values(client, user, food_item):
    MealEntry.objects.create(user=user, food=food_item, grams=Decimal("620.00"))
    DailyLog.objects.create(user=user, date=timezone.localdate(), hit_protein=False)

    response = client.get("/closeout/")

    assert response.status_code == 200
    assert response.context["suggestions"]["hit_protein"] is True
    assert response.context["form"].instance.hit_protein is False


def test_closeout_saves_daily_log_closed_at_and_weight(client, user):
    response = client.post(
        "/closeout/",
        {
            "walked_minutes": "35",
            "steps": "4200",
            "hit_protein": "on",
            "under_calories": "on",
            "walked_30": "on",
            "ate_breakfast": "on",
            "notes": "Good adherence day.",
            "weight_kg": "119.40",
            "weight_notes": "Tuesday weigh-in.",
        },
    )

    assert response.status_code == 302
    log = DailyLog.objects.get(user=user, date=timezone.localdate())
    assert log.closed_at is not None
    assert log.walked_minutes == 35
    assert log.walked_30 is True
    assert log.no_alcohol_or_sugar is False
    weight = WeightEntry.objects.get(user=user, date=timezone.localdate())
    assert weight.weight_kg == Decimal("119.40")
    assert weight.notes == "Tuesday weigh-in."


def test_summary_shows_closeout_consistency(client, user):
    """A closed day surfaces a streak of 1 in the consistency block."""
    DailyLog.objects.create(
        user=user,
        date=timezone.localdate(),
        hit_protein=True,
        under_calories=True,
        closed_at=timezone.now(),
    )

    response = client.get("/summary/")

    assert response.status_code == 200
    assert response.context["summary"]["consistency"]["closeout_streak"] == 1
    # Pluralisation: "1 day" not "1 days".
    assert b"Closeout streak" in response.content
    assert b">1 day<" in response.content
    # And the "Edit closeout" link appears on today's summary because the
    # day has a non-null ``closed_at``.
    assert b"Edit closeout" in response.content


def test_summary_shows_close_out_link_when_not_closed(client, user):
    """An open day shows the "Close out →" CTA instead of "Edit closeout"."""
    response = client.get("/summary/")

    assert response.status_code == 200
    assert response.context["summary"]["closed_at"] is None
    assert b"Close out \xe2\x86\x92" in response.content
    assert b"Day not closed yet" in response.content


def test_food_create_page_adds_food(client):
    response = client.post(
        "/foods/add/",
        {
            "name": "Test guava",
            "kcal_per_100g": "68.00",
            "protein_g": "2.60",
            "fat_g": "1.00",
            "carb_g": "14.30",
            "satiety_index": "180",
            "common_unit": "1 fruit = 55g",
            "default_grams": "55.00",
            "notes": "Local fruit test row",
        },
    )

    assert response.status_code == 302
    food = FoodItem.objects.get(name="Test guava")
    assert food.default_grams == Decimal("55.00")


def test_recipe_create_page_adds_recipe_with_item(client, food_item):
    response = client.post(
        "/recipes/add/",
        {
            "name": "Test chicken plate",
            "category": MealTemplate.CATEGORY_LUNCH,
            "notes": "Simple test recipe",
            "items-TOTAL_FORMS": "3",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-food": str(food_item.id),
            "items-0-grams": "200.00",
            "items-1-food": "",
            "items-1-grams": "",
            "items-2-food": "",
            "items-2-grams": "",
        },
    )

    assert response.status_code == 302
    recipe = MealTemplate.objects.get(name="Test chicken plate")
    assert recipe.items.count() == 1
    assert recipe.items.get().grams == Decimal("200.00")


def test_logged_meals_page_updates_and_deletes_rows(client, user, food_item):
    meal = MealEntry.objects.create(user=user, food=food_item, grams=Decimal("200.00"))

    update_response = client.post(
        "/meals/",
        {"meal_id": meal.id, "action": "update", "grams": "125.00"},
    )

    assert update_response.status_code == 302
    meal.refresh_from_db()
    assert meal.grams == Decimal("125.00")

    delete_response = client.post(
        "/meals/",
        {"meal_id": meal.id, "action": "delete"},
    )

    assert delete_response.status_code == 302
    assert not MealEntry.objects.filter(pk=meal.id).exists()
