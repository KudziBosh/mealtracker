"""Seed the Recipe Bank from ``01-full-plan.docx`` into ``MealTemplate``.

Recipes are reproduced as faithfully as the existing food seed allows:

* Ingredient names are mapped to existing ``FoodItem`` rows where possible.
* A handful of foods the recipes reference but the original 30-item seed did
  not include are added here in the same migration (pumpkin seeds, green
  pepper, carrot, mixed beans, mushrooms, sardines) so every line can be
  encoded as ``(FoodItem, grams)``.
* Negligible flavour ingredients (garlic, ginger, spring onion, chilli, soy
  sauce, lemon, salt) are intentionally dropped — they contribute < 5 kcal
  each and would dilute the macro signal.
* Where the plan doc specifies dry weights (e.g. "80 g brown rice (dry)") the
  seed records the cooked equivalent, because the existing ``FoodItem`` rows
  are cooked-state values.

A second pass at the end backfills ``default_grams`` for the new foods so the
form-prefill path covers them too.
"""

from __future__ import annotations

from decimal import Decimal

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

# --- New foods the recipes reference -----------------------------------------

NEW_FOOD_ITEMS = [
    {
        "name": "Pumpkin seeds, raw",
        "kcal_per_100g": "559.00",
        "protein_g": "30.20",
        "fat_g": "49.00",
        "carb_g": "10.70",
        "satiety_index": 170,
        "common_unit": "1 tablespoon = 8g",
        "default_grams": "8.00",
        "notes": "High-satiety topping. Used in the Greek yoghurt power bowl.",
    },
    {
        "name": "Green pepper, raw",
        "kcal_per_100g": "20.00",
        "protein_g": "0.90",
        "fat_g": "0.20",
        "carb_g": "4.60",
        "satiety_index": 180,
        "common_unit": "1 medium = 120g",
        "default_grams": "120.00",
        "notes": "Bell pepper / capsicum. Volume vegetable, low kcal.",
    },
    {
        "name": "Carrot, raw",
        "kcal_per_100g": "41.00",
        "protein_g": "0.90",
        "fat_g": "0.20",
        "carb_g": "9.60",
        "satiety_index": 200,
        "common_unit": "1 medium = 60g",
        "default_grams": "60.00",
        "notes": "Holt-style estimate; raw root vegetable.",
    },
    {
        "name": "Mixed beans, cooked",
        "kcal_per_100g": "127.00",
        "protein_g": "8.70",
        "fat_g": "0.50",
        "carb_g": "22.80",
        "satiety_index": 168,
        "common_unit": "1 cup cooked = 180g",
        "default_grams": "180.00",
        "notes": "Sugar beans / cowpeas, cooked. Holt satiety score for beans.",
    },
    {
        "name": "Mushrooms, cooked",
        "kcal_per_100g": "28.00",
        "protein_g": "2.20",
        "fat_g": "0.50",
        "carb_g": "5.30",
        "satiety_index": 150,
        "common_unit": "1 cup sliced = 156g",
        "default_grams": "156.00",
        "notes": "Mixed cooked mushrooms. Used in Chinese-style stir-fries.",
    },
    {
        "name": "Sardines, canned in water",
        "kcal_per_100g": "185.00",
        "protein_g": "24.00",
        "fat_g": "9.00",
        "carb_g": "0.00",
        "satiety_index": 225,
        "common_unit": "1 drained can = 90g",
        "default_grams": "90.00",
        "notes": "Holt-style estimate from canned fish. Same slot as canned tuna.",
    },
]


# --- Recipes -----------------------------------------------------------------
#
# Format: (name, category, [(food_name_fragment, grams), ...], notes)
#
# Food name fragments use case-insensitive substring match against ``FoodItem.
# name``. The first match wins, so fragments are written tight enough to avoid
# collisions (e.g. "Chicken breast" not "Chicken").

RECIPES = [
    # ---- Breakfast -----------------------------------------------------
    (
        "Potato & Egg Skillet",
        "breakfast",
        [
            ("Regular potato", 200),
            ("Whole egg", 200),  # 4 eggs × 50g
            ("Tomato", 120),
            ("Onion", 55),       # half medium
            ("Kale", 50),
            ("Olive oil", 5),
        ],
        "Highest-satiety breakfast option. ~560 kcal, 42 g protein.",
    ),
    (
        "Greek Yoghurt Power Bowl",
        "breakfast",
        [
            ("Greek yoghurt, plain full-fat", 300),
            ("Peanut butter", 16),
            ("Banana", 118),
            ("Pumpkin seeds", 10),
        ],
        "Assembly breakfast for rushed mornings. ~540 kcal, 38 g protein.",
    ),
    (
        "Kapenta & Tomato Scramble",
        "breakfast",
        [
            ("Kapenta", 50),
            ("Whole egg", 150),
            ("Tomato", 120),
            ("Onion", 55),
            ("Olive oil", 5),
            ("Brown bread", 35),
        ],
        "High-protein local breakfast. ~530 kcal, 45 g protein.",
    ),
    (
        "Eggs on Toast with Tomato",
        "breakfast",
        [
            ("Whole egg", 150),
            ("Brown bread", 70),
            ("Tomato", 120),
            ("Olive oil", 5),
        ],
        "Desk-rush option. ~510 kcal, 32 g protein.",
    ),
    (
        "Sweet Potato & Egg Hash",
        "breakfast",
        [
            ("Sweet potato", 200),
            ("Whole egg", 150),
            ("Onion", 55),
            ("Green pepper", 60),
            ("Olive oil", 5),
        ],
        "~560 kcal, 38 g protein.",
    ),
    (
        "Pumpkin & Egg Bowl",
        "breakfast",
        [
            ("Pumpkin", 250),
            ("Whole egg", 150),
            ("Tomato", 120),
            ("Olive oil", 5),
            ("Cottage cheese", 50),
        ],
        "Slightly sweet, very filling. ~520 kcal, 35 g protein.",
    ),
    # ---- Lunch ---------------------------------------------------------
    (
        "Chicken & Sweet Potato Plate",
        "lunch",
        [
            ("Chicken breast", 200),
            ("Sweet potato", 200),
            ("Kale", 100),
            ("Tomato", 120),
            ("Olive oil", 5),
        ],
        "~640 kcal, 52 g protein.",
    ),
    (
        "Beef Mince Stir-fry",
        "lunch",
        [
            ("Lean beef mince", 200),
            ("Brown rice, cooked", 200),  # 80 g dry ≈ 200 g cooked
            ("Cabbage", 80),
            ("Carrot", 60),
            ("Green pepper", 60),
            ("Onion", 55),
            ("Olive oil", 5),
        ],
        "~660 kcal, 48 g protein.",
    ),
    (
        "Tuna Salad Bowl",
        "lunch",
        [
            ("Canned tuna", 120),
            ("Regular potato", 170),
            ("Whole egg", 100),  # 2 eggs
            ("Tomato", 120),
            ("Onion", 30),
            ("Olive oil", 5),
        ],
        "Cold lunch with pre-prepped components. ~620 kcal, 50 g protein.",
    ),
    (
        "Chicken & Bean Bowl",
        "lunch",
        [
            ("Chicken breast", 180),
            ("Mixed beans, cooked", 180),
            ("Pumpkin", 100),
            ("Tomato", 120),
            ("Olive oil", 5),
        ],
        "~660 kcal, 55 g protein. Beans bring slow-burning carbs.",
    ),
    (
        "Kapenta, Sadza & Greens",
        "lunch",
        [
            ("Kapenta", 60),
            ("Sadza", 180),  # 60 g dry mealie meal ≈ 180 g cooked sadza
            ("Kale", 150),
            ("Tomato", 60),
            ("Onion", 30),
            ("Olive oil", 5),
        ],
        "Traditional, portion-controlled. ~640 kcal, 48 g protein.",
    ),
    (
        "Egg & Vegetable Curry",
        "lunch",
        [
            ("Whole egg", 200),  # 4 boiled eggs
            ("Tomato", 240),
            ("Onion", 110),
            ("Cabbage", 80),
            ("Carrot", 60),
            ("Brown rice, cooked", 200),
            ("Olive oil", 5),
        ],
        "~620 kcal, 32 g protein.",
    ),
    # ---- Dinner --------------------------------------------------------
    (
        "Pan-seared Kapenta with Pumpkin",
        "dinner",
        [
            ("Kapenta", 70),
            ("Pumpkin", 250),
            ("Kale", 150),
            ("Tomato", 60),
            ("Onion", 55),
            ("Olive oil", 5),
        ],
        "Cheapest high-protein dinner in Zimbabwe. ~490 kcal, 58 g protein.",
    ),
    (
        "Beef Mince & Sweet Potato",
        "dinner",
        [
            ("Lean beef mince", 200),
            ("Sweet potato", 200),
            ("Cabbage", 150),
            ("Tomato", 60),
            ("Onion", 55),
            ("Olive oil", 5),
        ],
        "~510 kcal, 55 g protein.",
    ),
    (
        "Grilled Broiler Quarters",
        "dinner",
        [
            ("Chicken thigh", 250),
            ("Pumpkin", 200),
            ("Kale", 100),
            ("Olive oil", 5),
        ],
        "Skin off saves ~150 kcal. ~500 kcal, 62 g protein.",
    ),
    (
        "Fish Tray Bake",
        "dinner",
        [
            ("River bream", 200),
            ("Sweet potato", 200),
            ("Kale", 100),
            ("Olive oil", 5),
        ],
        "Fish = #2 on satiety index. ~480 kcal, 55 g protein.",
    ),
    (
        "Bean & Vegetable Stew with Eggs",
        "dinner",
        [
            ("Mixed beans, cooked", 270),
            ("Onion", 110),
            ("Tomato", 240),
            ("Carrot", 60),
            ("Green pepper", 60),
            ("Whole egg", 100),  # 2 hard-boiled
            ("Olive oil", 5),
        ],
        "~470 kcal, 32 g protein + 2 eggs lift.",
    ),
    (
        "Chicken & Vegetable Soup (1 serving)",
        "dinner",
        [
            ("Chicken breast", 165),  # 500 g / 3 servings
            ("Carrot", 60),
            ("Onion", 60),
            ("Mixed beans, cooked", 90),
            ("Kale", 60),
            ("Brown rice, cooked", 50),
        ],
        "One of three servings from the 500g chicken batch. ~490 kcal, 50 g protein.",
    ),
    # ---- Snack ---------------------------------------------------------
    (
        "Yoghurt + PB + Fruit (snack)",
        "snack",
        [
            ("Greek yoghurt, plain full-fat", 250),
            ("Peanut butter", 16),
            ("Apple", 130),
        ],
        "The default snack. ~320 kcal, 28 g protein.",
    ),
    (
        "Eggs + Fruit (snack)",
        "snack",
        [
            ("Whole egg", 150),
            ("Apple", 180),
        ],
        "Grab and go. ~280 kcal, 20 g protein.",
    ),
    (
        "Cottage Cheese Bowl (snack)",
        "snack",
        [
            ("Cottage cheese", 200),
            ("Tomato", 60),
        ],
        "Highest protein per calorie. ~300 kcal, 32 g protein.",
    ),
    (
        "Apple + Peanut Butter (snack)",
        "snack",
        [
            ("Apple", 180),
            ("Peanut butter", 24),  # 1.5 tbsp
        ],
        "Lower-protein snack — use on high-protein days. ~260 kcal, 8 g protein.",
    ),
    # ---- Chinese-style -------------------------------------------------
    (
        "Steamed Ginger & Spring Onion Chicken",
        "chinese",
        [
            ("Chicken breast", 250),
            ("Brown rice, cooked", 200),
            ("Bok choy", 150),
            ("Sesame oil", 5),
        ],
        "Zero added cooking oil. ~480 kcal, 55 g protein.",
    ),
    (
        "Beef & Broccoli Stir-fry",
        "chinese",
        [
            ("Lean beef mince", 200),  # closest stand-in for sirloin slices
            ("Broccoli", 250),
            ("Onion", 55),
            ("Brown rice, cooked", 200),
            ("Sesame oil", 5),
        ],
        "~580 kcal, 50 g protein.",
    ),
    (
        "Tofu & Mixed Vegetable Stir-fry",
        "chinese",
        [
            ("Firm tofu", 250),
            ("Bok choy", 120),
            ("Mushrooms", 156),
            ("Green pepper", 60),
            ("Brown rice, cooked", 200),
            ("Sesame oil", 5),
        ],
        "Vegetarian. ~550 kcal, 38 g protein.",
    ),
    (
        "Steamed Egg with Chicken Mince",
        "chinese",
        [
            ("Whole egg", 200),
            ("Chicken breast", 100),  # mince stand-in
            ("Kale", 100),
            ("Brown rice, cooked", 150),
            ("Sesame oil", 5),
        ],
        "Cantonese steamed egg comfort food. ~440 kcal, 42 g protein.",
    ),
    (
        "Chicken & Vegetable Hot Pot (1 serving)",
        "chinese",
        [
            ("Chicken breast", 100),  # 200g across 2 servings
            ("Cabbage", 100),
            ("Bok choy", 100),
            ("Mushrooms", 50),
        ],
        "Broth-based, one of the highest-satiety recipes. ~430 kcal, 48 g protein.",
    ),
    (
        "Chicken Lettuce Wraps",
        "chinese",
        [
            ("Chicken breast", 250),
            ("Onion", 55),
            ("Carrot", 30),
            ("Sesame oil", 5),
        ],
        "San Choy Bow style. Lettuce volume is filling. ~470 kcal, 48 g protein.",
    ),
]


def _resolve_food(FoodItem, fragment: str):
    """Return the FoodItem whose name contains ``fragment`` (case-insensitive).

    Fail loud on miss — the migration is checked in, so any mismatch needs to
    be fixed at authoring time, not silently dropped at deploy time.
    """
    food = (
        FoodItem.objects.filter(name__icontains=fragment).order_by("name").first()
    )
    if food is None:
        raise LookupError(f"No FoodItem matched fragment: {fragment!r}")
    return food


def populate(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    FoodItem = apps.get_model("tracker", "FoodItem")
    MealTemplate = apps.get_model("tracker", "MealTemplate")
    MealTemplateItem = apps.get_model("tracker", "MealTemplateItem")

    # --- 1) New foods (idempotent on name) -----------------------------
    for spec in NEW_FOOD_ITEMS:
        FoodItem.objects.update_or_create(
            name=spec["name"],
            defaults={
                "kcal_per_100g": Decimal(spec["kcal_per_100g"]),
                "protein_g": Decimal(spec["protein_g"]),
                "fat_g": Decimal(spec["fat_g"]),
                "carb_g": Decimal(spec["carb_g"]),
                "satiety_index": spec["satiety_index"],
                "common_unit": spec["common_unit"],
                "default_grams": Decimal(spec["default_grams"]),
                "notes": spec["notes"],
            },
        )

    # --- 2) Recipes ----------------------------------------------------
    for name, category, items, notes in RECIPES:
        template, _ = MealTemplate.objects.update_or_create(
            name=name,
            defaults={"category": category, "notes": notes},
        )
        # Replace items wholesale so re-running the migration doesn't
        # leave orphaned ingredients if a recipe was edited upstream.
        template.items.all().delete()
        for fragment, grams in items:
            food = _resolve_food(FoodItem, fragment)
            MealTemplateItem.objects.create(
                meal_template=template,
                food=food,
                grams=Decimal(str(grams)),
            )


def unpopulate(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    MealTemplate = apps.get_model("tracker", "MealTemplate")
    FoodItem = apps.get_model("tracker", "FoodItem")
    MealTemplate.objects.filter(name__in=[r[0] for r in RECIPES]).delete()
    FoodItem.objects.filter(name__in=[f["name"] for f in NEW_FOOD_ITEMS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0007_meal_templates"),
    ]

    operations = [
        migrations.RunPython(populate, reverse_code=unpopulate),
    ]
