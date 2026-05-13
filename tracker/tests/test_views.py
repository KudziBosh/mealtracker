"""Focused tests for the server-rendered dashboard and HTMX endpoints."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from tracker import protocol
from tracker.food_sources import FoodCandidate
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


# ---- Retroactive closeout ----------------------------------------------


def test_closeout_for_yesterday_renders_and_saves(client, user, food_item):
    """A missed day can be closed out within the late window."""
    yesterday = timezone.localdate() - timedelta(days=1)

    # Render: form pre-fills walking, sees the retroactive banner.
    render = client.get(f"/closeout/{yesterday.isoformat()}/")
    assert render.status_code == 200
    assert render.context["target_date"] == yesterday
    assert render.context["days_late"] == 1
    assert render.context["is_today"] is False
    assert b"day late" in render.content
    assert b"Closeout \xc2\xb7" in render.content  # title uses · separator

    # Save: closed_at gets stamped and the redirect points at yesterday's summary.
    save = client.post(
        f"/closeout/{yesterday.isoformat()}/",
        {
            "walked_minutes": "42",
            "steps": "5500",
            "hit_protein": "on",
            "under_calories": "on",
            "walked_30": "on",
            "ate_breakfast": "on",
            "notes": "Caught up next morning.",
            "weight_kg": "118.90",
            "weight_notes": "",
        },
    )
    assert save.status_code == 302
    assert save.url == f"/summary/{yesterday.isoformat()}/"
    log = DailyLog.objects.get(user=user, date=yesterday)
    assert log.closed_at is not None
    assert log.walked_minutes == 42
    # Weight is upserted against the *target* date, not today.
    weight = WeightEntry.objects.get(user=user, date=yesterday)
    assert weight.weight_kg == Decimal("118.90")


def test_closeout_rejects_future_dates(client):
    tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
    assert client.get(f"/closeout/{tomorrow}/").status_code == 404


def test_closeout_rejects_dates_outside_late_window(client):
    too_old = timezone.localdate() - timedelta(days=protocol.CLOSEOUT_LATE_DAYS_MAX + 1)
    assert client.get(f"/closeout/{too_old.isoformat()}/").status_code == 404


def test_closeout_rejects_malformed_date(client):
    assert client.get("/closeout/not-a-date/").status_code == 404


def test_summary_shows_close_out_cta_on_past_unclosed_day_in_window(client):
    """Viewing yesterday's summary surfaces a working closeout CTA."""
    yesterday = timezone.localdate() - timedelta(days=1)

    response = client.get(f"/summary/{yesterday.isoformat()}/")

    assert response.status_code == 200
    assert response.context["summary"]["closeout_window_open"] is True
    assert response.context["summary"]["days_late"] == 1
    assert f"/closeout/{yesterday.isoformat()}/".encode() in response.content
    assert b"window still open" in response.content


def test_summary_hides_close_out_cta_outside_window(client):
    """A day older than the window has no working closeout CTA."""
    too_old = timezone.localdate() - timedelta(days=protocol.CLOSEOUT_LATE_DAYS_MAX + 3)

    response = client.get(f"/summary/{too_old.isoformat()}/")

    assert response.status_code == 200
    assert response.context["summary"]["closeout_window_open"] is False
    # No working close-out link to this date should appear.
    assert f"/closeout/{too_old.isoformat()}/".encode() not in response.content
    assert b"Window has expired" in response.content


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


# ---- External food-source lookups --------------------------------------


def _candidate(
    source: str = "FDC",
    source_id: str = "171477",
    name: str = "Chicken, broiler, breast, meat only, cooked, roasted",
    **overrides,
) -> FoodCandidate:
    """Build a fully-populated FoodCandidate for view tests."""
    defaults = {
        "source": source,
        "source_id": source_id,
        "source_url": f"https://example/{source.lower()}/{source_id}",
        "name": name,
        "kcal_per_100g": Decimal("165.00"),
        "protein_g": Decimal("31.02"),
        "fat_g": Decimal("3.57"),
        "carb_g": Decimal("0.00"),
        "description": "Poultry Products",
    }
    defaults.update(overrides)
    return FoodCandidate(**defaults)


def test_food_external_search_renders_results_from_both_sources(client):
    fdc = _candidate(source="FDC", source_id="171477")
    off = _candidate(source="OFF", source_id="0028400090000", name="Smooth Peanut Butter")

    with patch("tracker.views.combined_search", return_value=[fdc, off]) as mock_search:
        response = client.get("/htmx/foods/external-search/?q=chicken")

    mock_search.assert_called_once_with("chicken")
    assert response.status_code == 200
    assert b"171477" in response.content
    assert b"FDC" in response.content
    assert b"OFF" in response.content
    assert b"Smooth Peanut Butter" in response.content


def test_food_external_search_blank_query_shows_no_results(client):
    """Mid-typing fires reach here with empty q; render an empty panel, not 400."""
    with patch("tracker.views.combined_search") as mock_search:
        response = client.get("/htmx/foods/external-search/?q=")

    mock_search.assert_not_called()
    assert response.status_code == 200
    # The empty-state copy doesn't render either (no query, no candidates).
    assert b"No matches" not in response.content


def test_food_external_search_no_matches_renders_friendly_empty_state(client):
    with patch("tracker.views.combined_search", return_value=[]):
        response = client.get("/htmx/foods/external-search/?q=kapenta")

    assert response.status_code == 200
    assert b"No matches" in response.content
    assert b"Zimbabwean" in response.content  # local-food hint


def test_food_add_with_candidate_param_prefills_form(client):
    fdc = _candidate(source="FDC", source_id="171477")

    with patch("tracker.views.fetch_candidate", return_value=fdc) as mock_fetch:
        response = client.get("/foods/add/?candidate=FDC:171477")

    mock_fetch.assert_called_once_with("FDC", "171477")
    assert response.status_code == 200
    initial = response.context["form"].initial
    assert initial["name"].startswith("Chicken")
    assert initial["kcal_per_100g"] == Decimal("165.00")
    assert initial["source"] == "FDC"
    assert initial["source_id"] == "171477"
    # The "Prefilled from FDC" banner appears in the rendered page.
    assert b"Prefilled from" in response.content
    assert b"FDC" in response.content


def test_food_add_with_unknown_candidate_falls_back_to_blank_form(client):
    """If the source layer can't resolve the candidate, render the empty form."""
    with patch("tracker.views.fetch_candidate", return_value=None):
        response = client.get("/foods/add/?candidate=FDC:does-not-exist")

    assert response.status_code == 200
    assert response.context["form"].initial == {}
    assert b"Prefilled from" not in response.content


def test_food_add_persists_source_fields_on_save(client):
    """An imported food saves with the full provenance trio."""
    response = client.post(
        "/foods/add/",
        {
            "name": "Chicken breast, cooked",
            "kcal_per_100g": "165.00",
            "protein_g": "31.02",
            "fat_g": "3.57",
            "carb_g": "0.00",
            "satiety_index": "225",
            "common_unit": "100g cooked",
            "default_grams": "150.00",
            "notes": "Imported from FDC",
            "source": "FDC",
            "source_id": "171477",
            "source_url": "https://fdc.nal.usda.gov/food-details/171477/nutrients",
        },
    )

    assert response.status_code == 302
    food = FoodItem.objects.get(name="Chicken breast, cooked")
    assert food.source == "FDC"
    assert food.source_id == "171477"
    assert food.source_url.endswith("/food-details/171477/nutrients")


def test_food_list_shows_source_badges(client):
    """An imported row shows an FDC/OFF badge; a manual row shows none."""
    # Filter the response to just these two rows so seeded data doesn't
    # influence the badge count.
    FoodItem.objects.create(
        name="Zzz-test manual kapenta",
        kcal_per_100g=Decimal("265.00"),
        protein_g=Decimal("60.00"),
        fat_g=Decimal("8.00"),
        carb_g=Decimal("0.00"),
        common_unit="100g dried",
    )
    FoodItem.objects.create(
        name="Zzz-test FDC chicken",
        kcal_per_100g=Decimal("165.00"),
        protein_g=Decimal("31.00"),
        fat_g=Decimal("3.57"),
        carb_g=Decimal("0.00"),
        common_unit="100g cooked",
        source="FDC",
        source_id="171477",
    )

    response = client.get("/foods/?q=Zzz-test")

    assert response.status_code == 200
    content = response.content.decode()
    assert "Zzz-test manual kapenta" in content
    assert "Zzz-test FDC chicken" in content
    # Exactly one FDC badge — only the FDC-imported row renders one.
    assert content.count(">FDC</span>") == 1
    # And no OFF badge appears for either row.
    assert ">OFF</span>" not in content
