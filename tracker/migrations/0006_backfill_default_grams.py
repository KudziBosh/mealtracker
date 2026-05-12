"""Backfill ``FoodItem.default_grams`` from the existing ``common_unit`` strings.

Every seeded ``common_unit`` follows the same pattern ``"<label> = <N>g"`` (e.g.
``"1 medium potato = 170g"``). The regex below pulls the last "Ng" out of the
string and writes it to the new column. Foods whose ``common_unit`` doesn't
parse stay NULL, which is the explicit "no sensible default" state.
"""

from __future__ import annotations

import re
from decimal import Decimal

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

# Anchored at the end of the string so "1 medium = 200g (cooked weight ~180g)"
# would still pick the *unit* number rather than the parenthetical aside. None
# of the seeded values currently use that form, but the anchor costs nothing.
_GRAMS_RE = re.compile(r"=\s*(\d+(?:\.\d+)?)\s*g\b", re.IGNORECASE)


def _grams_from_common_unit(common_unit: str) -> Decimal | None:
    if not common_unit:
        return None
    match = _GRAMS_RE.search(common_unit)
    if not match:
        return None
    return Decimal(match.group(1))


def populate(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    FoodItem = apps.get_model("tracker", "FoodItem")
    to_update = []
    for food in FoodItem.objects.filter(default_grams__isnull=True):
        parsed = _grams_from_common_unit(food.common_unit)
        if parsed is not None:
            food.default_grams = parsed
            to_update.append(food)
    if to_update:
        FoodItem.objects.bulk_update(to_update, fields=["default_grams"])


def unpopulate(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    FoodItem = apps.get_model("tracker", "FoodItem")
    FoodItem.objects.update(default_grams=None)


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0005_add_default_grams"),
    ]

    operations = [
        migrations.RunPython(populate, reverse_code=unpopulate),
    ]
