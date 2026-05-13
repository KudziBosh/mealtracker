"""Catch the food + recipe seeds up to the updated plan docs.

Sources:
- ``02-recipe-bank.docx`` — adds 10 recipes (Egg Muffins, Saucy Beef &
  Broccoli, Crispy Chicken Sandwich, Dill Pickle Chicken Salad,
  Stovetop Beef & Shells, Cajun Beef & Rice, Chicken & Asparagus
  Stir-fry, plus three smoothies).
- ``05-shopping-list.docx`` — pulls in 16 foods the new recipes
  reference (beef sirloin, soy chunks, mealie meal, asparagus,
  celery, red pepper, sesame seeds, bean sprouts, garlic, wholemeal
  burger bun, tomato passata, beef bouillon, Worcestershire, dill
  pickles, mustard, cornflour).

Idempotent: ``update_or_create`` on name, and each recipe's items are
wiped + re-created on re-run so any future macro tweaks land cleanly.
"""

from __future__ import annotations

from decimal import Decimal

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor


# --- New foods --------------------------------------------------------

NEW_FOOD_ITEMS: list[dict[str, object]] = [
    {
        "name": "Beef sirloin / rump, cooked",
        "kcal_per_100g": "217.00", "protein_g": "30.00", "fat_g": "10.00",
        "carb_g": "0.00", "satiety_index": 195,
        "common_unit": "1 portion = 150g", "default_grams": "150.00",
        "notes": "Lean cut, trimmed. Stand-in for stir-fry beef strips.",
    },
    {
        "name": "Soy chunks (TVP), dry",
        "kcal_per_100g": "333.00", "protein_g": "50.00", "fat_g": "2.00",
        "carb_g": "33.00", "satiety_index": 155,
        "common_unit": "1 portion dry = 30g (≈90g rehydrated)", "default_grams": "30.00",
        "notes": "Rehydrates ~3x. Plant protein source; lower bioavailability than animal protein.",
    },
    {
        "name": "Burger bun, wholemeal",
        "kcal_per_100g": "280.00", "protein_g": "10.00", "fat_g": "4.00",
        "carb_g": "50.00", "satiety_index": 125,
        "common_unit": "1 bun = 60g", "default_grams": "60.00",
        "notes": "Wholemeal/brioche bun. Lower satiety than brown sliced bread.",
    },
    {
        "name": "Mealie meal, dry",
        "kcal_per_100g": "362.00", "protein_g": "9.00", "fat_g": "4.00",
        "carb_g": "75.00", "satiety_index": 100,
        "common_unit": "1 small sadza portion = 60g", "default_grams": "60.00",
        "notes": "Raw maize meal; cooks ~3:1 to sadza. Use 'Sadza, cooked' when logging post-cook.",
    },
    {
        "name": "Celery, raw",
        "kcal_per_100g": "16.00", "protein_g": "0.70", "fat_g": "0.20",
        "carb_g": "3.00", "satiety_index": 200,
        "common_unit": "1 stalk = 40g", "default_grams": "40.00",
        "notes": "Holy-trinity flavour base (with onion + pepper) for Cajun dishes.",
    },
    {
        "name": "Red pepper, raw",
        "kcal_per_100g": "31.00", "protein_g": "1.00", "fat_g": "0.30",
        "carb_g": "6.00", "satiety_index": 180,
        "common_unit": "1 medium = 120g", "default_grams": "120.00",
        "notes": "Sweeter than green pepper; same volume vegetable role.",
    },
    {
        "name": "Asparagus, cooked",
        "kcal_per_100g": "22.00", "protein_g": "2.40", "fat_g": "0.20",
        "carb_g": "4.10", "satiety_index": 180,
        "common_unit": "1 cup cooked = 180g", "default_grams": "180.00",
        "notes": "Sub green beans or tender broccoli stems if asparagus unavailable.",
    },
    {
        "name": "Sesame seeds, raw",
        "kcal_per_100g": "573.00", "protein_g": "18.00", "fat_g": "50.00",
        "carb_g": "23.00", "satiety_index": 150,
        "common_unit": "1 tablespoon = 9g", "default_grams": "9.00",
        "notes": "Finishing topping for Chinese-style dishes; calorie-dense.",
    },
    {
        "name": "Bean sprouts (mung), raw",
        "kcal_per_100g": "30.00", "protein_g": "3.00", "fat_g": "0.20",
        "carb_g": "6.00", "satiety_index": 200,
        "common_unit": "1 cup = 100g", "default_grams": "100.00",
        "notes": "High water + fibre; volume vegetable for stir-fries.",
    },
    {
        "name": "Garlic, raw",
        "kcal_per_100g": "149.00", "protein_g": "6.40", "fat_g": "0.50",
        "carb_g": "33.00", "satiety_index": 120,
        "common_unit": "1 clove = 3g", "default_grams": "3.00",
        "notes": "Aromatic — small portions only. Listed so recipes can be modelled accurately.",
    },
    {
        "name": "Tomato passata (canned)",
        "kcal_per_100g": "32.00", "protein_g": "1.60", "fat_g": "0.30",
        "carb_g": "7.00", "satiety_index": 170,
        "common_unit": "1 cup = 240g", "default_grams": "240.00",
        "notes": "Strained pureed tomatoes. Substitute canned chopped tomatoes 1:1.",
    },
    {
        "name": "Beef bouillon cube",
        "kcal_per_100g": "198.00", "protein_g": "12.00", "fat_g": "12.00",
        "carb_g": "13.00", "satiety_index": 60,
        "common_unit": "1 cube = 4g", "default_grams": "4.00",
        "notes": "Highly concentrated; the 4g cube is what one cube of stock weighs.",
    },
    {
        "name": "Worcestershire sauce",
        "kcal_per_100g": "78.00", "protein_g": "0.00", "fat_g": "0.00",
        "carb_g": "19.00", "satiety_index": 60,
        "common_unit": "1 tablespoon = 18g", "default_grams": "18.00",
        "notes": "Used in small amounts; modest sugar content per teaspoon.",
    },
    {
        "name": "Dill cucumber pickles",
        "kcal_per_100g": "11.00", "protein_g": "0.50", "fat_g": "0.20",
        "carb_g": "2.30", "satiety_index": 200,
        "common_unit": "1 medium spear = 30g", "default_grams": "30.00",
        "notes": "Mostly brine + cucumber. Very low kcal; high salt.",
    },
    {
        "name": "Mustard (Dijon)",
        "kcal_per_100g": "66.00", "protein_g": "4.40", "fat_g": "4.00",
        "carb_g": "5.00", "satiety_index": 120,
        "common_unit": "1 teaspoon = 5g", "default_grams": "5.00",
        "notes": "Dijon or English style; same macros within rounding.",
    },
    {
        "name": "Cornflour (cornstarch)",
        "kcal_per_100g": "381.00", "protein_g": "0.30", "fat_g": "0.10",
        "carb_g": "91.00", "satiety_index": 80,
        "common_unit": "1 tablespoon = 8g", "default_grams": "8.00",
        "notes": "Pure starch thickener. Tiny amounts; tracked for completeness.",
    },
]


# --- New recipes ------------------------------------------------------
#
# Format mirrors 0008: (name, category, [(food_fragment, grams), ...], notes).
# Fragments are written tight enough to avoid collisions with the broader
# catalogue — e.g. "Beef sirloin" not "Beef".
#
# Cooking-loss convention: the source plan document lists meat amounts as
# bought (raw) weights, but every meat ``FoodItem`` row in this app stores
# cooked-state macros. Apply a ~25% water-loss adjustment when translating
# from raw to cooked: ``200 g raw chicken/beef → 150 g cooked``. That keeps
# the totals aligned with the doc's published macro targets.

RECIPES: list[tuple[str, str, list[tuple[str, float]], str]] = [
    # ---- Breakfast: new --------------------------------------------
    (
        "Egg Muffins (3 muffins + bread + fruit)",
        "breakfast",
        [
            # 3 muffins is 3/8 of the batch.
            ("Whole egg", 150),                   # 3 eggs
            ("Spinach, cooked", 67),              # 1/8 of 180g cup × 3
            ("Tomato, raw", 45),
            ("Onion, raw", 21),
            ("Cheddar cheese", 19),
            # Eaten with…
            ("Brown bread", 35),                  # 1 slice
            ("Banana, raw", 118),                 # 1 fruit
        ],
        "Batch-prep 8 muffins on Sunday; eat 3 with bread + fruit. ~540 kcal, 38 g protein per serving.",
    ),
    # ---- Lunch: new -------------------------------------------------
    (
        "Saucy Beef & Broccoli with Rice",
        "lunch",
        [
            ("Beef sirloin / rump, cooked", 150),  # 200 g raw → ~150 g cooked
            ("Broccoli, cooked", 200),
            ("Onion, raw", 55),
            ("Brown rice, cooked", 200),           # 80 g dry ≈ 200 g cooked
            ("Olive oil", 5),
            ("Beef bouillon cube", 4),
            ("White sugar", 4),                    # 1 tsp brown sugar
            ("Cornflour (cornstarch)", 6),
        ],
        "American-Chinese saucier B&B vs the classic stir-fry. ~620 kcal, 48 g protein.",
    ),
    (
        "Air-Fried Crispy Chicken Sandwich",
        "lunch",
        [
            ("Chicken breast", 150),               # 200 g raw → ~150 g cooked
            ("Cornflakes", 30),                    # crushed coating
            ("Whole egg", 35),                     # 2 tbsp egg whites stand-in
            ("Burger bun, wholemeal", 60),
            ("Greek yoghurt, plain low-fat", 30),
            ("Mustard (Dijon)", 5),
            ("Dill cucumber pickles", 15),         # 2 pickle slices
        ],
        "High-protein takeout fix. ~490 kcal, 50 g protein.",
    ),
    (
        "Dill Pickle Chicken Salad",
        "lunch",
        [
            ("Chicken breast", 150),               # 200 g raw → ~150 g cooked
            ("Greek yoghurt, plain low-fat", 150),
            ("Dill cucumber pickles", 30),
            ("Spring onion, raw", 15),
            ("Mustard (Dijon)", 5),
            ("Lettuce, raw", 80),                  # served in lettuce cups
        ],
        "Cold, portable, no-cook lunch. ~380 kcal, 45 g protein. Lettuce-cup variant.",
    ),
    # ---- Dinner: new ------------------------------------------------
    (
        "Stovetop Beef & Shells",
        "dinner",
        [
            ("Lean beef mince", 150),              # 200 g raw → ~150 g cooked
            ("Pasta, cooked", 140),                # 60 g dry shells ≈ 140 g cooked
            ("Tomato passata (canned)", 200),
            ("Onion, raw", 60),
            ("Garlic, raw", 6),                    # 2 cloves
            ("Beef bouillon cube", 4),
            ("Kale, cooked", 80),                  # side of stir-fried greens
        ],
        "Comfort-food pasta, dairy-free. ~530 kcal, 42 g protein.",
    ),
    (
        "Cajun Beef & Rice",
        "dinner",
        [
            ("Lean beef mince", 150),              # 200 g raw → ~150 g cooked
            ("Brown rice, cooked", 200),           # 80 g dry
            ("Celery, raw", 40),                   # 2 sticks chopped
            ("Green pepper, raw", 60),             # 1 small diced
            ("Red pepper, raw", 60),               # 1 small diced
            ("Onion, raw", 55),
            ("Beef bouillon cube", 4),
            ("Worcestershire sauce", 18),
        ],
        "One-pan Louisiana 'dirty rice' style. ~560 kcal, 40 g protein.",
    ),
    (
        "Chicken & Asparagus Stir-fry",
        "dinner",
        [
            ("Chicken breast", 150),               # 200 g raw → ~150 g cooked
            ("Asparagus, cooked", 175),            # 250 g raw cooks down ~70%
            ("Mushrooms, cooked", 50),             # 4 mushrooms sliced
            ("Carrot, raw", 60),                   # 1 in matchsticks
            ("Spring onion, raw", 30),             # 2 stalks
            ("Tomato, raw", 60),                   # 1 small in wedges
            ("Brown rice, cooked", 200),           # 80 g dry
            ("Garlic, raw", 6),                    # 2 cloves
            ("Olive oil", 5),
            ("Cornflour (cornstarch)", 6),
        ],
        "Saucy soy-thickened stir-fry. ~510 kcal, 52 g protein. Sub green beans for asparagus.",
    ),
    # ---- Snacks: new smoothies -------------------------------------
    (
        "Fruit & Milk Smoothie",
        "snack",
        [
            ("Low-fat milk (2%)", 250),
            ("Banana, raw", 118),
            ("Pear, raw", 130),
        ],
        "Lower-protein basic smoothie. ~280 kcal, 10 g protein. Pair with 2 eggs for snack total.",
    ),
    (
        "Soy Chunk Power Smoothie",
        "snack",
        [
            ("Soy chunks (TVP), dry", 30),
            ("Low-fat milk (2%)", 250),
            ("Banana, raw", 118),
            ("Pear, raw", 130),
            ("Honey", 7),                          # optional 1 tsp if tart
        ],
        "Plant-protein smoothie. ~330 kcal, 22 g effective protein.",
    ),
    (
        "Greek Yoghurt Smoothie",
        "snack",
        [
            # Low-fat Greek for the macro target. Sub full-fat by editing the
            # recipe in /recipes/<id>/edit/ if you prefer the creamier version.
            ("Greek yoghurt, plain low-fat", 200),
            ("Low-fat milk (2%)", 150),
            ("Banana, raw", 118),
            ("Pear, raw", 100),                    # 1 small pear
        ],
        "Highest-protein smoothie, most reliable. ~340 kcal, 25 g protein.",
    ),
]


def _resolve_food(FoodItem, fragment: str):
    """Same name-fragment resolver as 0008 (case-insensitive substring)."""
    food = FoodItem.objects.filter(name__icontains=fragment).order_by("name").first()
    if food is None:
        raise LookupError(f"No FoodItem matched fragment: {fragment!r}")
    return food


def populate(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    FoodItem = apps.get_model("tracker", "FoodItem")
    MealTemplate = apps.get_model("tracker", "MealTemplate")
    MealTemplateItem = apps.get_model("tracker", "MealTemplateItem")

    # --- 1) Foods ---------------------------------------------------
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

    # --- 2) Recipes -------------------------------------------------
    for name, category, items, notes in RECIPES:
        template, _ = MealTemplate.objects.update_or_create(
            name=name,
            defaults={"category": category, "notes": notes},
        )
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
    FoodItem.objects.filter(name__in=[spec["name"] for spec in NEW_FOOD_ITEMS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0009_seed_zimbabwe_foods"),
    ]

    operations = [
        migrations.RunPython(populate, reverse_code=unpopulate),
    ]
