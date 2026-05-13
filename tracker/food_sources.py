"""External food-data lookup helpers (USDA FoodData Central + Open Food Facts).

Adapters that translate two public nutrition APIs into a single normalized
``FoodCandidate`` shape the import view can prefill the FoodItem form with.
The local DB stays the source of truth — these calls happen once when the
owner adds a food, and the saved row records ``source`` / ``source_id`` /
``source_url`` so a future re-import can be one click.

Design notes:

* Both APIs return per-100g values, which maps directly to the model.
* ``FoodCandidate`` carries everything the form needs — no second detail
  call required for the search → import flow.
* All HTTP failures degrade gracefully: a single-source outage returns an
  empty list rather than 500-ing the page. The combined search just falls
  back to whichever provider is still up.
* The Holt 1995 ``satiety_index`` and the protocol-specific ``default_grams``
  are *not* in either dataset; the form keeps those blank for the owner to
  fill in by hand.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# Network timeouts kept short so a slow upstream can't hang the dashboard.
# (connect, read) seconds — generous enough for Harare-side latency.
_HTTP_TIMEOUT = (3.0, 8.0)

# Open Food Facts requires a descriptive User-Agent identifying the app +
# contact. Hitting their search endpoint with the requests default UA now
# returns 403 Forbidden. The string format is what their API docs call out.
_USER_AGENT = "Mealtracker/0.2 (self-hosted; +https://github.com/KudziBosh/mealtracker)"
_DEFAULT_HEADERS = {"User-Agent": _USER_AGENT}

# Result caps. The owner is one person picking one food at a time — a wall of
# 25 rows isn't useful and bloats response payload.
_PER_SOURCE_LIMIT = 8

# Public API endpoints.
_FDC_SEARCH_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"
_FDC_PRODUCT_URL_FMT = "https://fdc.nal.usda.gov/food-details/{fdc_id}/nutrients"
_OFF_SEARCH_URL = "https://world.openfoodfacts.org/cgi/search.pl"
_OFF_PRODUCT_URL_FMT = "https://world.openfoodfacts.org/product/{code}"

# FDC nutrient IDs we care about. ``Energy`` has two flavours (kcal vs kJ);
# we always prefer the kcal row (1008) and fall back to converting from kJ
# (1062) so foods that only report kilojoules still produce a kcal value.
_FDC_NUTRIENT_ID_KCAL = 1008
_FDC_NUTRIENT_ID_KCAL_LEGACY = 2047  # older "Energy (Atwater General Factors)"
_FDC_NUTRIENT_ID_KJ = 1062
_FDC_NUTRIENT_ID_PROTEIN = 1003
_FDC_NUTRIENT_ID_FAT = 1004
_FDC_NUTRIENT_ID_CARB = 1005


@dataclass(frozen=True)
class FoodCandidate:
    """One row of search results, source-agnostic and ready for form prefill."""

    source: str
    source_id: str
    source_url: str
    name: str
    kcal_per_100g: Decimal
    protein_g: Decimal
    fat_g: Decimal
    carb_g: Decimal
    description: str = ""


# ---- Decimal coercion -----------------------------------------------------


def _as_decimal(value: Any) -> Decimal:
    """Return ``Decimal(value)`` or ``Decimal(0)`` on any malformed input.

    APIs occasionally return ``None``, empty strings, floats, or — for
    the worst-case OFF rows — bare ``NaN`` floats. ``Decimal(str(float('nan')))``
    parses to ``Decimal('NaN')``, which would explode on ``.quantize`` and
    on the model's DecimalField. So we treat NaN as missing and return zero.
    """
    if value in (None, ""):
        return Decimal("0")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")
    if parsed.is_nan() or parsed.is_infinite():
        return Decimal("0")
    return parsed.quantize(Decimal("0.01"))


# ---- USDA FoodData Central -------------------------------------------------


def _extract_fdc_nutrient(food: dict, nutrient_id: int) -> Decimal | None:
    """Pull a single nutrient value from FDC's per-food ``foodNutrients`` list."""
    for row in food.get("foodNutrients", []) or []:
        candidate = row.get("nutrientId") or (row.get("nutrient") or {}).get("id")
        if candidate == nutrient_id:
            value = row.get("value")
            if value is None:
                value = row.get("amount")
            if value is None:
                continue
            return _as_decimal(value)
    return None


def _fdc_kcal_per_100g(food: dict) -> Decimal:
    """Best-effort kcal/100g from an FDC food row, converting kJ if needed."""
    for nutrient_id in (_FDC_NUTRIENT_ID_KCAL, _FDC_NUTRIENT_ID_KCAL_LEGACY):
        value = _extract_fdc_nutrient(food, nutrient_id)
        if value is not None and value > 0:
            return value
    kj = _extract_fdc_nutrient(food, _FDC_NUTRIENT_ID_KJ)
    if kj is not None and kj > 0:
        # 1 kcal = 4.184 kJ. Quantize to keep numbers stable.
        return (kj / Decimal("4.184")).quantize(Decimal("0.01"))
    return Decimal("0")


def _fdc_food_to_candidate(food: dict) -> FoodCandidate | None:
    """Map one FDC food dict into a ``FoodCandidate``, or ``None`` if invalid."""
    fdc_id = food.get("fdcId")
    if not fdc_id:
        return None
    name = (food.get("description") or "").strip()
    if not name:
        return None
    kcal = _fdc_kcal_per_100g(food)
    protein = _extract_fdc_nutrient(food, _FDC_NUTRIENT_ID_PROTEIN) or Decimal("0")
    fat = _extract_fdc_nutrient(food, _FDC_NUTRIENT_ID_FAT) or Decimal("0")
    carb = _extract_fdc_nutrient(food, _FDC_NUTRIENT_ID_CARB) or Decimal("0")
    return FoodCandidate(
        source="FDC",
        source_id=str(fdc_id),
        source_url=_FDC_PRODUCT_URL_FMT.format(fdc_id=fdc_id),
        name=name,
        kcal_per_100g=kcal,
        protein_g=protein,
        fat_g=fat,
        carb_g=carb,
        description=(food.get("foodCategory") or food.get("dataType") or ""),
    )


def search_fdc(query: str, *, api_key: str | None = None) -> list[FoodCandidate]:
    """Search USDA FoodData Central; return ``[]`` if no key or on any error.

    Restricted to the curated Foundation + SR Legacy datasets — they hold
    the well-vetted raw-ingredient rows that map cleanly to the protocol's
    meal-plan foods. The huge Branded dataset is left for Open Food Facts.
    """
    key = api_key if api_key is not None else getattr(settings, "USDA_FDC_API_KEY", "")
    if not key or not query.strip():
        return []
    params = {
        "api_key": key,
        "query": query,
        "pageSize": _PER_SOURCE_LIMIT,
        "dataType": "Foundation,SR Legacy",
    }
    try:
        response = requests.get(
            _FDC_SEARCH_URL,
            params=params,
            headers=_DEFAULT_HEADERS,
            timeout=_HTTP_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("FDC search failed for %r: %s", query, exc)
        return []
    candidates = []
    for food in payload.get("foods", []) or []:
        candidate = _fdc_food_to_candidate(food)
        if candidate is None:
            continue
        # USDA's search response occasionally omits nutrient values for
        # certain rows even when the detail endpoint has them. We can't
        # afford a detail call per row, so drop the un-decideable ones
        # rather than show "0 kcal / 0 g P" entries that aren't useful.
        if candidate.kcal_per_100g == 0 and candidate.protein_g == 0:
            continue
        candidates.append(candidate)
    return candidates


# ---- Open Food Facts -------------------------------------------------------


def _off_product_to_candidate(product: dict) -> FoodCandidate | None:
    """Map one OFF product dict into a ``FoodCandidate``, or ``None`` if invalid."""
    code = product.get("code")
    if not code:
        return None
    name = (
        product.get("product_name_en")
        or product.get("product_name")
        or product.get("generic_name")
        or ""
    ).strip()
    if not name:
        return None
    nutriments = product.get("nutriments", {}) or {}
    kcal = nutriments.get("energy-kcal_100g")
    if kcal in (None, ""):
        kj = nutriments.get("energy_100g") or nutriments.get("energy-kj_100g")
        if kj not in (None, ""):
            kcal = float(kj) / 4.184
    return FoodCandidate(
        source="OFF",
        source_id=str(code),
        source_url=_OFF_PRODUCT_URL_FMT.format(code=code),
        name=name,
        kcal_per_100g=_as_decimal(kcal),
        protein_g=_as_decimal(nutriments.get("proteins_100g")),
        fat_g=_as_decimal(nutriments.get("fat_100g")),
        carb_g=_as_decimal(nutriments.get("carbohydrates_100g")),
        description=(product.get("brands") or "").strip(),
    )


def search_off(query: str) -> list[FoodCandidate]:
    """Search Open Food Facts; returns ``[]`` on any error."""
    if not query.strip():
        return []
    params = {
        "search_terms": query,
        "search_simple": 1,
        "action": "process",
        "json": 1,
        "page_size": _PER_SOURCE_LIMIT,
        "fields": (
            "code,product_name,product_name_en,generic_name,brands,nutriments"
        ),
    }
    try:
        response = requests.get(
            _OFF_SEARCH_URL,
            params=params,
            headers=_DEFAULT_HEADERS,
            timeout=_HTTP_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("OFF search failed for %r: %s", query, exc)
        return []
    candidates = []
    for product in payload.get("products", []) or []:
        candidate = _off_product_to_candidate(product)
        if candidate is None:
            continue
        # Skip rows with no usable macros — OFF has a lot of half-curated
        # entries where the nutriments object is empty.
        if candidate.kcal_per_100g == 0 and candidate.protein_g == 0:
            continue
        candidates.append(candidate)
    return candidates


# ---- Combined search ------------------------------------------------------


def combined_search(query: str) -> list[FoodCandidate]:
    """Search FDC + OFF concurrently and return the merged list, FDC first.

    FDC rows are surfaced first because they're the higher-quality, vetted
    set for raw ingredients — the bulk of the meal-plan foods. OFF results
    follow for branded items / non-US products the FDC database doesn't
    carry. No dedup heuristic across sources; the source badge makes it
    visually obvious which row is which.

    The two upstream calls run in parallel via a small thread pool — both
    are pure I/O, sequential calls were the dominant latency on the search
    page (~7-8s combined). Threads (not asyncio) because both providers'
    clients are sync ``requests`` and we never have more than two in flight.
    """
    if not query.strip():
        return []
    with ThreadPoolExecutor(max_workers=2) as pool:
        fdc_future = pool.submit(search_fdc, query)
        off_future = pool.submit(search_off, query)
        return [*fdc_future.result(), *off_future.result()]


def fetch_candidate(source: str, source_id: str) -> FoodCandidate | None:
    """Re-fetch one candidate by source + id, for the import-preview view.

    Search results already carry everything the form needs, so this is only
    used when the user lands directly on the import URL with no prior search
    state (e.g. via the bookmark/back button). Returns ``None`` on miss.
    """
    if source == "FDC":
        return _fetch_fdc(source_id)
    if source == "OFF":
        return _fetch_off(source_id)
    return None


def _fetch_fdc(fdc_id: str) -> FoodCandidate | None:
    key = getattr(settings, "USDA_FDC_API_KEY", "")
    if not key:
        return None
    try:
        response = requests.get(
            f"https://api.nal.usda.gov/fdc/v1/food/{fdc_id}",
            params={"api_key": key},
            headers=_DEFAULT_HEADERS,
            timeout=_HTTP_TIMEOUT,
        )
        response.raise_for_status()
        return _fdc_food_to_candidate(response.json())
    except (requests.RequestException, ValueError) as exc:
        logger.warning("FDC detail fetch failed for %s: %s", fdc_id, exc)
        return None


def _fetch_off(code: str) -> FoodCandidate | None:
    try:
        response = requests.get(
            f"https://world.openfoodfacts.org/api/v2/product/{code}.json",
            headers=_DEFAULT_HEADERS,
            timeout=_HTTP_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("OFF detail fetch failed for %s: %s", code, exc)
        return None
    if payload.get("status") != 1:
        return None
    return _off_product_to_candidate(payload.get("product", {}) or {})
