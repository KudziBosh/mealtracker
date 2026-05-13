"""Add chaofan (炒饭) and chao mian (炒面) — plan-aligned versions.

Restaurant versions of these dishes are deep-fried-oil and big-portion. The
plan's Chinese-style section is explicit about the variant we want:

* "Stir-frying with 1 tsp oil — not the restaurant 3 tbsp"
* "Keep brown rice to 80 g dry weight max" (≈ 200 g cooked)
* "Fried noodles in oil — boil noodles instead, toss with sauce at the end"

So both recipes here use a single teaspoon of sesame oil as a finisher
(not a cooking medium), a controlled brown-rice portion, and pasta cooked
the boiled-then-tossed way as our nearest stand-in for Chinese egg noodles.

All ingredients already exist in the catalogue — this migration adds two
``MealTemplate`` rows only. Idempotent: ``update_or_create`` on name,
items wiped + re-created on re-run.

Cooking-loss convention from 0010 applies: meat is in cooked weight,
i.e. 200 g raw chicken breast → 150 g cooked.
"""

from __future__ import annotations

from decimal import Decimal

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor


RECIPES: list[tuple[str, str, list[tuple[str, float]], str]] = [
    (
        "Chaofan (Chicken Fried Rice, plan-aligned)",
        "chinese",
        [
            ("Chicken breast", 150),               # 200 g raw → ~150 g cooked
            ("Brown rice, cooked", 150),           # 60 g dry rice
            ("Whole egg", 50),                     # 1 egg scrambled in
            ("Carrot, raw", 60),                   # diced fine
            ("Peas, cooked", 80),
            ("Spring onion, raw", 30),             # 2 stalks
            ("Bean sprouts (mung), raw", 100),     # added at the end for crunch
            ("Garlic, raw", 3),                    # 1 clove
            ("Sesame oil", 5),                     # 1 tsp finisher, not cooking
        ],
        (
            "Day-after fried rice with cold rice — works best when the rice "
            "was cooked the night before and chilled. Use a hot dry pan: "
            "scramble the egg first, set aside; stir-fry chicken with garlic; "
            "add carrot, peas; stir in cold rice; fold egg + bean sprouts + "
            "spring onion through; drizzle sesame oil to finish. Zero added "
            "cooking oil — fat comes from the sesame finisher only. "
            "Approx 640 kcal, 64 g protein."
        ),
    ),
    (
        "Chao Mian (Chicken Chow Mein, plan-aligned)",
        "chinese",
        [
            ("Chicken breast", 150),               # 200 g raw → ~150 g cooked
            ("Pasta, cooked", 140),                # 60 g dry noodles ≈ 140 g cooked
            ("Cabbage, cooked", 100),              # napa or regular cabbage shredded
            ("Bean sprouts (mung), raw", 100),
            ("Carrot, raw", 60),                   # matchsticks
            ("Mushrooms, cooked", 50),
            ("Spring onion, raw", 30),
            ("Garlic, raw", 3),                    # 1 clove
            ("Sesame oil", 5),                     # 1 tsp finisher
        ],
        (
            "Boiled-noodle chow mein — not the deep-fried restaurant version. "
            "Boil pasta to al dente, drain, set aside. Stir-fry chicken with "
            "garlic in a dry-hot pan. Add mushroom, carrot, cabbage; stir-fry "
            "3 min. Toss in noodles + bean sprouts + spring onion; finish "
            "with sesame oil and a splash of low-sodium soy. "
            "Approx 620 kcal, 62 g protein."
        ),
    ),
]


def _resolve_food(FoodItem, fragment: str):
    food = FoodItem.objects.filter(name__icontains=fragment).order_by("name").first()
    if food is None:
        raise LookupError(f"No FoodItem matched fragment: {fragment!r}")
    return food


def populate(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    FoodItem = apps.get_model("tracker", "FoodItem")
    MealTemplate = apps.get_model("tracker", "MealTemplate")
    MealTemplateItem = apps.get_model("tracker", "MealTemplateItem")

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
    MealTemplate.objects.filter(name__in=[r[0] for r in RECIPES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0010_seed_updated_recipe_bank"),
    ]

    operations = [
        migrations.RunPython(populate, reverse_code=unpopulate),
    ]
