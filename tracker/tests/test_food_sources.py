"""Tests for the FDC + Open Food Facts adapters.

HTTP is mocked at the ``requests.get`` boundary so the suite stays offline-
deterministic and never hits a real upstream. We assert two things:

* the JSON shapes the real APIs return parse into a complete ``FoodCandidate``
  (no zero-macros sneaking through unless they're truly zero in the source);
* upstream failures degrade silently — an outage on one provider must not
  break the combined search.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest
import requests

from tracker.food_sources import (
    FoodCandidate,
    combined_search,
    fetch_candidate,
    search_fdc,
    search_off,
)


def _fake_response(payload: dict, *, status: int = 200):
    """Lightweight stand-in for a ``requests.Response`` covering what we use."""

    class _Resp:
        status_code = status

        def json(self):
            return payload

        def raise_for_status(self):
            if status >= 400:
                raise requests.HTTPError(f"HTTP {status}")

    return _Resp()


# ---- FDC -----------------------------------------------------------------


_FDC_CHICKEN_SEARCH = {
    "foods": [
        {
            "fdcId": 171477,
            "description": "Chicken, broiler, breast, meat only, cooked, roasted",
            "dataType": "SR Legacy",
            "foodCategory": "Poultry Products",
            "foodNutrients": [
                {"nutrientId": 1008, "value": 165.0},
                {"nutrientId": 1003, "value": 31.02},
                {"nutrientId": 1004, "value": 3.57},
                {"nutrientId": 1005, "value": 0.0},
            ],
        }
    ]
}


def test_search_fdc_parses_macros_correctly():
    with patch("tracker.food_sources.requests.get", return_value=_fake_response(_FDC_CHICKEN_SEARCH)):
        results = search_fdc("chicken breast", api_key="test-key")

    assert len(results) == 1
    chicken = results[0]
    assert chicken.source == "FDC"
    assert chicken.source_id == "171477"
    assert chicken.name.startswith("Chicken, broiler, breast")
    assert chicken.kcal_per_100g == Decimal("165.00")
    assert chicken.protein_g == Decimal("31.02")
    assert chicken.fat_g == Decimal("3.57")
    assert chicken.carb_g == Decimal("0.00")
    assert "fdc.nal.usda.gov" in chicken.source_url


def test_search_fdc_returns_empty_when_no_api_key():
    """No key configured ⇒ skip the call entirely (don't 401 the upstream)."""
    with patch("tracker.food_sources.requests.get") as mock_get:
        assert search_fdc("anything", api_key="") == []
        mock_get.assert_not_called()


def test_search_fdc_returns_empty_on_http_error():
    with patch(
        "tracker.food_sources.requests.get",
        side_effect=requests.ConnectionError("Network unreachable"),
    ):
        assert search_fdc("anything", api_key="test-key") == []


def test_search_fdc_drops_rows_with_no_useful_macros():
    """USDA's search response sometimes omits nutrients; drop those rows."""
    payload = {
        "foods": [
            {
                "fdcId": 1,
                "description": "Real row",
                "foodNutrients": [
                    {"nutrientId": 1008, "value": 120},
                    {"nutrientId": 1003, "value": 8},
                ],
            },
            {
                # No nutrient values — these creep into FDC's search response
                # for some legacy rows. Useless to display.
                "fdcId": 2,
                "description": "Empty row",
                "foodNutrients": [],
            },
        ]
    }
    with patch("tracker.food_sources.requests.get", return_value=_fake_response(payload)):
        results = search_fdc("foo", api_key="test-key")

    assert [r.name for r in results] == ["Real row"]


def test_search_fdc_converts_kj_to_kcal_when_kcal_missing():
    """Some FDC rows only report kJ — we must still surface a usable kcal."""
    payload = {
        "foods": [
            {
                "fdcId": 999,
                "description": "Foo with only kJ",
                "foodNutrients": [
                    {"nutrientId": 1062, "value": 836.8},  # 836.8 kJ / 4.184 = 200
                    {"nutrientId": 1003, "value": 10},
                ],
            }
        ]
    }
    with patch("tracker.food_sources.requests.get", return_value=_fake_response(payload)):
        results = search_fdc("foo", api_key="test-key")

    assert len(results) == 1
    assert results[0].kcal_per_100g == Decimal("200.00")


# ---- Open Food Facts -----------------------------------------------------


_OFF_PEANUT_BUTTER_SEARCH = {
    "products": [
        {
            "code": "0028400090000",
            "product_name": "Smooth Peanut Butter",
            "product_name_en": "Smooth Peanut Butter",
            "brands": "Genuine Brand",
            "nutriments": {
                "energy-kcal_100g": 588,
                "proteins_100g": 25.0,
                "fat_100g": 50.0,
                "carbohydrates_100g": 20.0,
            },
        }
    ]
}


def test_search_off_parses_macros_correctly():
    with patch(
        "tracker.food_sources.requests.get", return_value=_fake_response(_OFF_PEANUT_BUTTER_SEARCH)
    ):
        results = search_off("peanut butter")

    assert len(results) == 1
    pb = results[0]
    assert pb.source == "OFF"
    assert pb.source_id == "0028400090000"
    assert pb.name == "Smooth Peanut Butter"
    assert pb.kcal_per_100g == Decimal("588.00")
    assert pb.protein_g == Decimal("25.00")
    assert pb.description == "Genuine Brand"
    assert "openfoodfacts.org/product/0028400090000" in pb.source_url


def test_search_off_skips_rows_with_no_macros():
    """OFF carries plenty of half-curated rows; drop them so the list is useful."""
    payload = {
        "products": [
            {"code": "1", "product_name": "Empty", "nutriments": {}},
            {
                "code": "2",
                "product_name": "Full",
                "nutriments": {"energy-kcal_100g": 100, "proteins_100g": 5},
            },
        ]
    }
    with patch("tracker.food_sources.requests.get", return_value=_fake_response(payload)):
        results = search_off("foo")
    assert [r.name for r in results] == ["Full"]


def test_search_off_returns_empty_on_http_error():
    with patch(
        "tracker.food_sources.requests.get", side_effect=requests.Timeout("slow")
    ):
        assert search_off("anything") == []


# ---- Combined ------------------------------------------------------------


def test_combined_search_lists_fdc_first_then_off():
    """FDC rows always come before OFF rows in the merged list."""
    fdc_row = FoodCandidate(
        source="FDC", source_id="1", source_url="u", name="FDC item",
        kcal_per_100g=Decimal("100"), protein_g=Decimal("10"),
        fat_g=Decimal("1"), carb_g=Decimal("1"),
    )
    off_row = FoodCandidate(
        source="OFF", source_id="2", source_url="u", name="OFF item",
        kcal_per_100g=Decimal("200"), protein_g=Decimal("5"),
        fat_g=Decimal("2"), carb_g=Decimal("2"),
    )
    with patch("tracker.food_sources.search_fdc", return_value=[fdc_row]), \
         patch("tracker.food_sources.search_off", return_value=[off_row]):
        results = combined_search("anything")

    assert [r.source for r in results] == ["FDC", "OFF"]


def test_combined_search_works_when_fdc_is_down():
    """A single-source outage degrades to the other source, not 500."""
    off_row = FoodCandidate(
        source="OFF", source_id="2", source_url="u", name="OFF item",
        kcal_per_100g=Decimal("100"), protein_g=Decimal("5"),
        fat_g=Decimal("1"), carb_g=Decimal("1"),
    )
    with patch("tracker.food_sources.search_fdc", return_value=[]), \
         patch("tracker.food_sources.search_off", return_value=[off_row]):
        results = combined_search("peanut butter")

    assert [r.source for r in results] == ["OFF"]


def test_combined_search_blank_query_returns_empty_without_calling_either_source():
    """An empty query short-circuits both providers."""
    with patch("tracker.food_sources.search_fdc") as fdc_mock, \
         patch("tracker.food_sources.search_off") as off_mock:
        assert combined_search("   ") == []
        fdc_mock.assert_not_called()
        off_mock.assert_not_called()


# ---- fetch_candidate -----------------------------------------------------


def test_fetch_candidate_fdc_returns_full_row(settings):
    settings.USDA_FDC_API_KEY = "test-key"
    detail = _FDC_CHICKEN_SEARCH["foods"][0]
    with patch("tracker.food_sources.requests.get", return_value=_fake_response(detail)):
        result = fetch_candidate("FDC", "171477")

    assert isinstance(result, FoodCandidate)
    assert result.source_id == "171477"
    assert result.kcal_per_100g == Decimal("165.00")


def test_fetch_candidate_off_returns_full_row():
    payload = {"status": 1, "product": _OFF_PEANUT_BUTTER_SEARCH["products"][0]}
    with patch("tracker.food_sources.requests.get", return_value=_fake_response(payload)):
        result = fetch_candidate("OFF", "0028400090000")

    assert isinstance(result, FoodCandidate)
    assert result.protein_g == Decimal("25.00")


def test_fetch_candidate_off_returns_none_for_missing_product():
    """OFF responds 200 with ``status: 0`` for an unknown barcode."""
    with patch(
        "tracker.food_sources.requests.get",
        return_value=_fake_response({"status": 0}),
    ):
        assert fetch_candidate("OFF", "0000000000000") is None


def test_fetch_candidate_unknown_source_returns_none():
    with patch("tracker.food_sources.requests.get") as mock_get:
        assert fetch_candidate("EDAMAM", "anything") is None
        mock_get.assert_not_called()


@pytest.mark.parametrize("garbage_value", [None, "", "not-a-number", float("nan")])
def test_decimal_coercion_swallows_bad_values(garbage_value):
    """Malformed numeric values from upstream must not bubble Decimal errors."""
    payload = {
        "products": [
            {
                "code": "1",
                "product_name": "Garbage row",
                "nutriments": {
                    "energy-kcal_100g": 100,
                    "proteins_100g": garbage_value,
                    "fat_100g": 1,
                    "carbohydrates_100g": 1,
                },
            }
        ]
    }
    with patch("tracker.food_sources.requests.get", return_value=_fake_response(payload)):
        results = search_off("anything")

    # Garbage protein is coerced to 0; the row still surfaces because kcal is real.
    assert len(results) == 1
    assert results[0].protein_g == Decimal("0")
