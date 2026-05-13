"""Broaden the food catalogue with day-to-day Zimbabwean items.

The original 0003 seed was tight (30 plan-aligned items); the meal-template
seed added another 6 recipe-specific foods. This migration grows the
catalogue to roughly 90 by covering the kinds of foods someone in Harare
actually opens the fridge to: more fruits and vegetables, dairy (including
*amasi*/sour milk), staple starches (white rice, pasta, oats, cornflakes),
common protein cuts (pork, bacon, boerewors, goat, chicken liver), nuts and
seeds, common sauces, and — deliberately — sugary drinks and alcohol so the
"no sugary drinks / no alcohol" habit has the right rows to log against.

Macros are per 100 g / 100 ml of the as-eaten form. Satiety indices are
Holt 1995 where available, estimated against the white-bread = 100 baseline
elsewhere (high-protein-and-water foods score higher; fat-and-sugar dense
ones score lower).

The seed is idempotent on ``name`` via ``update_or_create`` so re-running
the migration won't double-create rows.
"""

from __future__ import annotations

from decimal import Decimal

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor


# Each entry: name, kcal/100g, protein/100g, fat/100g, carb/100g, satiety,
# common_unit (free text), default_grams (numeric portion), notes.
FOOD_ITEMS: list[dict[str, object]] = [
    # ---- Fruits ------------------------------------------------------
    {
        "name": "Avocado, raw",
        "kcal_per_100g": "160.00", "protein_g": "2.00", "fat_g": "14.70",
        "carb_g": "8.50", "satiety_index": 150,
        "common_unit": "1 medium avocado = 150g",
        "default_grams": "150.00",
        "notes": "Fat-heavy fruit; holds well between meals despite low protein.",
    },
    {
        "name": "Pawpaw (papaya), raw",
        "kcal_per_100g": "43.00", "protein_g": "0.50", "fat_g": "0.30",
        "carb_g": "11.00", "satiety_index": 210,
        "common_unit": "1 cup cubes = 145g",
        "default_grams": "145.00",
        "notes": "High water and fibre. Common ZW breakfast or snack.",
    },
    {
        "name": "Watermelon, raw",
        "kcal_per_100g": "30.00", "protein_g": "0.60", "fat_g": "0.20",
        "carb_g": "7.60", "satiety_index": 200,
        "common_unit": "1 cup diced = 152g",
        "default_grams": "152.00",
        "notes": "Mostly water — high satiety per kcal, but easy to over-eat by volume.",
    },
    {
        "name": "Pineapple, raw",
        "kcal_per_100g": "50.00", "protein_g": "0.50", "fat_g": "0.10",
        "carb_g": "13.00", "satiety_index": 180,
        "common_unit": "1 cup chunks = 165g",
        "default_grams": "165.00",
        "notes": "Higher natural sugar than melon — moderate satiety.",
    },
    {
        "name": "Guava, raw",
        "kcal_per_100g": "68.00", "protein_g": "2.60", "fat_g": "1.00",
        "carb_g": "14.00", "satiety_index": 200,
        "common_unit": "1 medium guava = 55g",
        "default_grams": "55.00",
        "notes": "Highest fibre of common ZW fruits — strong satiety per kcal.",
    },
    {
        "name": "Lemon, raw",
        "kcal_per_100g": "29.00", "protein_g": "1.10", "fat_g": "0.30",
        "carb_g": "9.30", "satiety_index": 140,
        "common_unit": "1 medium lemon = 60g",
        "default_grams": "60.00",
        "notes": "Almost never eaten alone — track when used as a flavour base.",
    },
    {
        "name": "Pear, raw",
        "kcal_per_100g": "57.00", "protein_g": "0.40", "fat_g": "0.10",
        "carb_g": "15.00", "satiety_index": 200,
        "common_unit": "1 medium pear = 178g",
        "default_grams": "178.00",
        "notes": "Estimated using the same fibre-fruit pattern as apple.",
    },
    {
        "name": "Peach, raw",
        "kcal_per_100g": "39.00", "protein_g": "0.90", "fat_g": "0.30",
        "carb_g": "10.00", "satiety_index": 180,
        "common_unit": "1 medium peach = 150g",
        "default_grams": "150.00",
        "notes": "Stone fruit; satiety estimate from comparable raw fruits.",
    },
    {
        "name": "Grapes, raw",
        "kcal_per_100g": "69.00", "protein_g": "0.70", "fat_g": "0.20",
        "carb_g": "18.00", "satiety_index": 140,
        "common_unit": "1 cup = 150g",
        "default_grams": "150.00",
        "notes": "Easy to over-eat by handful; lower satiety than whole-fruit pieces.",
    },
    {
        "name": "Strawberries, raw",
        "kcal_per_100g": "32.00", "protein_g": "0.70", "fat_g": "0.30",
        "carb_g": "7.70", "satiety_index": 200,
        "common_unit": "1 cup halves = 152g",
        "default_grams": "152.00",
        "notes": "High water + fibre.",
    },
    # ---- Vegetables --------------------------------------------------
    {
        "name": "Spinach, cooked",
        "kcal_per_100g": "23.00", "protein_g": "3.00", "fat_g": "0.30",
        "carb_g": "3.80", "satiety_index": 180,
        "common_unit": "1 cup cooked = 180g",
        "default_grams": "180.00",
        "notes": "Volume vegetable; iron-rich.",
    },
    {
        "name": "Lettuce, raw",
        "kcal_per_100g": "15.00", "protein_g": "1.40", "fat_g": "0.20",
        "carb_g": "2.90", "satiety_index": 200,
        "common_unit": "1 cup shredded = 36g",
        "default_grams": "36.00",
        "notes": "Mostly water.",
    },
    {
        "name": "Cucumber, raw",
        "kcal_per_100g": "16.00", "protein_g": "0.70", "fat_g": "0.10",
        "carb_g": "3.60", "satiety_index": 200,
        "common_unit": "1 medium cucumber = 200g",
        "default_grams": "200.00",
        "notes": "Volume vegetable.",
    },
    {
        "name": "Cauliflower, cooked",
        "kcal_per_100g": "23.00", "protein_g": "1.80", "fat_g": "0.50",
        "carb_g": "4.10", "satiety_index": 170,
        "common_unit": "1 cup chopped = 124g",
        "default_grams": "124.00",
        "notes": "Substitutes well for rice when steaming.",
    },
    {
        "name": "Beetroot, cooked",
        "kcal_per_100g": "44.00", "protein_g": "1.70", "fat_g": "0.20",
        "carb_g": "10.00", "satiety_index": 170,
        "common_unit": "1 cup sliced = 170g",
        "default_grams": "170.00",
        "notes": "Common ZW salad component.",
    },
    {
        "name": "Butternut, cooked",
        "kcal_per_100g": "39.00", "protein_g": "0.90", "fat_g": "0.10",
        "carb_g": "10.00", "satiety_index": 175,
        "common_unit": "1 cup cubes = 205g",
        "default_grams": "205.00",
        "notes": "Sweet squash; interchangeable with pumpkin in most recipes.",
    },
    {
        "name": "Spring onion, raw",
        "kcal_per_100g": "32.00", "protein_g": "1.80", "fat_g": "0.20",
        "carb_g": "7.30", "satiety_index": 140,
        "common_unit": "1 stalk = 15g",
        "default_grams": "15.00",
        "notes": "Flavour aromatic; small portions.",
    },
    {
        "name": "Sweet corn, cooked",
        "kcal_per_100g": "86.00", "protein_g": "3.30", "fat_g": "1.40",
        "carb_g": "19.00", "satiety_index": 155,
        "common_unit": "1 medium cob = 90g",
        "default_grams": "90.00",
        "notes": "Higher carb than other vegetables.",
    },
    {
        "name": "Green beans, cooked",
        "kcal_per_100g": "35.00", "protein_g": "1.90", "fat_g": "0.30",
        "carb_g": "7.90", "satiety_index": 170,
        "common_unit": "1 cup = 125g",
        "default_grams": "125.00",
        "notes": "Common stir-fry vegetable.",
    },
    {
        "name": "Peas, cooked",
        "kcal_per_100g": "84.00", "protein_g": "5.40", "fat_g": "0.40",
        "carb_g": "16.00", "satiety_index": 160,
        "common_unit": "1 cup = 160g",
        "default_grams": "160.00",
        "notes": "Higher protein than other green veg.",
    },
    {
        "name": "Okra, cooked",
        "kcal_per_100g": "22.00", "protein_g": "1.90", "fat_g": "0.20",
        "carb_g": "4.50", "satiety_index": 170,
        "common_unit": "1 cup = 160g",
        "default_grams": "160.00",
        "notes": "Common in ZW stews.",
    },
    {
        "name": "Covo (rape), cooked",
        "kcal_per_100g": "26.00", "protein_g": "2.60", "fat_g": "0.50",
        "carb_g": "4.50", "satiety_index": 180,
        "common_unit": "1 cup cooked = 170g",
        "default_grams": "170.00",
        "notes": "Local mustard greens; classic ZW vegetable side.",
    },
    # ---- Dairy -------------------------------------------------------
    {
        "name": "Whole milk",
        "kcal_per_100g": "61.00", "protein_g": "3.20", "fat_g": "3.30",
        "carb_g": "4.80", "satiety_index": 120,
        "common_unit": "1 cup = 245g",
        "default_grams": "245.00",
        "notes": "Per 100 ml. Standard Dairibord whole milk.",
    },
    {
        "name": "Low-fat milk (2%)",
        "kcal_per_100g": "50.00", "protein_g": "3.40", "fat_g": "2.00",
        "carb_g": "5.00", "satiety_index": 125,
        "common_unit": "1 cup = 245g",
        "default_grams": "245.00",
        "notes": "Per 100 ml.",
    },
    {
        "name": "Amasi / sour milk (Hodzeko)",
        "kcal_per_100g": "59.00", "protein_g": "3.30", "fat_g": "3.00",
        "carb_g": "4.50", "satiety_index": 135,
        "common_unit": "1 cup = 245g",
        "default_grams": "245.00",
        "notes": "Fermented sour milk; classic with sadza. Slightly higher satiety than fresh milk.",
    },
    {
        "name": "Cheddar cheese",
        "kcal_per_100g": "402.00", "protein_g": "25.00", "fat_g": "33.00",
        "carb_g": "1.30", "satiety_index": 150,
        "common_unit": "1 slice = 28g",
        "default_grams": "28.00",
        "notes": "Calorie-dense; small portions go a long way.",
    },
    {
        "name": "Butter",
        "kcal_per_100g": "717.00", "protein_g": "0.90", "fat_g": "81.00",
        "carb_g": "0.10", "satiety_index": 80,
        "common_unit": "1 tablespoon = 14g",
        "default_grams": "14.00",
        "notes": "Almost pure fat; track honestly when spread on toast.",
    },
    {
        "name": "Yoghurt, plain regular",
        "kcal_per_100g": "61.00", "protein_g": "3.50", "fat_g": "3.30",
        "carb_g": "4.70", "satiety_index": 125,
        "common_unit": "1 cup = 245g",
        "default_grams": "245.00",
        "notes": "Non-Greek plain yoghurt (e.g. Dairibord). Lower protein than Greek.",
    },
    # ---- Starches & grains ------------------------------------------
    {
        "name": "White bread",
        "kcal_per_100g": "265.00", "protein_g": "9.00", "fat_g": "3.20",
        "carb_g": "49.00", "satiety_index": 100,
        "common_unit": "1 slice = 30g",
        "default_grams": "30.00",
        "notes": "Holt 1995 baseline = 100. Lower satiety than brown.",
    },
    {
        "name": "White rice, cooked",
        "kcal_per_100g": "130.00", "protein_g": "2.70", "fat_g": "0.30",
        "carb_g": "28.00", "satiety_index": 138,
        "common_unit": "1 cup cooked = 158g",
        "default_grams": "158.00",
        "notes": "Holt 1995 value for white rice.",
    },
    {
        "name": "Pasta, cooked",
        "kcal_per_100g": "158.00", "protein_g": "5.80", "fat_g": "0.90",
        "carb_g": "31.00", "satiety_index": 119,
        "common_unit": "1 cup cooked = 140g",
        "default_grams": "140.00",
        "notes": "Holt 1995 value for white pasta.",
    },
    {
        "name": "Rolled oats, cooked porridge",
        "kcal_per_100g": "71.00", "protein_g": "2.50", "fat_g": "1.50",
        "carb_g": "12.00", "satiety_index": 209,
        "common_unit": "1 cup cooked = 234g",
        "default_grams": "234.00",
        "notes": "Holt 1995 value for porridge. Use plain rolled oats, not instant.",
    },
    {
        "name": "Cornflakes",
        "kcal_per_100g": "357.00", "protein_g": "7.50", "fat_g": "0.40",
        "carb_g": "84.00", "satiety_index": 118,
        "common_unit": "1 cup = 28g",
        "default_grams": "28.00",
        "notes": "Holt 1995 value. Low satiety — supplement with protein.",
    },
    {
        "name": "Maputi (popped maize)",
        "kcal_per_100g": "387.00", "protein_g": "13.00", "fat_g": "5.00",
        "carb_g": "78.00", "satiety_index": 154,
        "common_unit": "1 small handful = 15g",
        "default_grams": "15.00",
        "notes": "Holt 1995 satiety for popcorn (high volume per kcal).",
    },
    {
        "name": "Cowpeas (nyemba), cooked",
        "kcal_per_100g": "116.00", "protein_g": "7.70", "fat_g": "0.50",
        "carb_g": "21.00", "satiety_index": 170,
        "common_unit": "1 cup cooked = 170g",
        "default_grams": "170.00",
        "notes": "Local cowpeas, slightly different macros to mixed beans.",
    },
    # ---- Proteins ----------------------------------------------------
    {
        "name": "Pork chops, cooked lean",
        "kcal_per_100g": "231.00", "protein_g": "31.00", "fat_g": "11.00",
        "carb_g": "0.00", "satiety_index": 190,
        "common_unit": "1 chop = 130g",
        "default_grams": "130.00",
        "notes": "Lean pork loin, trimmed.",
    },
    {
        "name": "Bacon, cooked",
        "kcal_per_100g": "541.00", "protein_g": "37.00", "fat_g": "42.00",
        "carb_g": "1.40", "satiety_index": 170,
        "common_unit": "1 strip = 8g",
        "default_grams": "8.00",
        "notes": "Calorie-dense; portion creep is the main risk.",
    },
    {
        "name": "Boerewors, cooked",
        "kcal_per_100g": "318.00", "protein_g": "18.00", "fat_g": "27.00",
        "carb_g": "0.00", "satiety_index": 150,
        "common_unit": "1 average length = 100g",
        "default_grams": "100.00",
        "notes": "Fat content varies wildly by butcher; ~30 % fat typical.",
    },
    {
        "name": "T-bone steak, cooked",
        "kcal_per_100g": "286.00", "protein_g": "27.00", "fat_g": "19.00",
        "carb_g": "0.00", "satiety_index": 190,
        "common_unit": "1 steak = 200g",
        "default_grams": "200.00",
        "notes": "Includes some bone-edge fat. For lean cuts use sirloin instead.",
    },
    {
        "name": "Goat meat, cooked",
        "kcal_per_100g": "143.00", "protein_g": "27.00", "fat_g": "3.00",
        "carb_g": "0.00", "satiety_index": 200,
        "common_unit": "1 portion = 150g",
        "default_grams": "150.00",
        "notes": "Leaner than beef; very high satiety per kcal.",
    },
    {
        "name": "Roast chicken with skin",
        "kcal_per_100g": "239.00", "protein_g": "27.00", "fat_g": "14.00",
        "carb_g": "0.00", "satiety_index": 185,
        "common_unit": "1 quarter = 200g",
        "default_grams": "200.00",
        "notes": "Skin-on roast. Remove skin to save ~150 kcal per quarter.",
    },
    {
        "name": "Chicken liver, cooked",
        "kcal_per_100g": "167.00", "protein_g": "25.00", "fat_g": "6.50",
        "carb_g": "1.40", "satiety_index": 210,
        "common_unit": "1 portion = 80g",
        "default_grams": "80.00",
        "notes": "Very high protein and iron per kcal.",
    },
    {
        "name": "Lentils, cooked",
        "kcal_per_100g": "116.00", "protein_g": "9.00", "fat_g": "0.40",
        "carb_g": "20.00", "satiety_index": 170,
        "common_unit": "1 cup cooked = 198g",
        "default_grams": "198.00",
        "notes": "Higher protein per kcal than rice or pasta.",
    },
    # ---- Nuts & seeds ------------------------------------------------
    {
        "name": "Almonds, raw",
        "kcal_per_100g": "579.00", "protein_g": "21.00", "fat_g": "50.00",
        "carb_g": "22.00", "satiety_index": 170,
        "common_unit": "1 small handful = 28g",
        "default_grams": "28.00",
        "notes": "Snack-sized portion; calorie creep is the risk.",
    },
    {
        "name": "Cashews, raw",
        "kcal_per_100g": "553.00", "protein_g": "18.00", "fat_g": "44.00",
        "carb_g": "30.00", "satiety_index": 140,
        "common_unit": "1 small handful = 28g",
        "default_grams": "28.00",
        "notes": "Higher carb than almonds; easier to overeat.",
    },
    {
        "name": "Sunflower seeds, raw",
        "kcal_per_100g": "584.00", "protein_g": "21.00", "fat_g": "51.00",
        "carb_g": "20.00", "satiety_index": 150,
        "common_unit": "1 tablespoon = 9g",
        "default_grams": "9.00",
        "notes": "Calorie-dense topping for yoghurt or salad.",
    },
    # ---- Sauces, sweeteners, spreads --------------------------------
    {
        "name": "White sugar",
        "kcal_per_100g": "387.00", "protein_g": "0.00", "fat_g": "0.00",
        "carb_g": "100.00", "satiety_index": 50,
        "common_unit": "1 teaspoon = 4g",
        "default_grams": "4.00",
        "notes": "Tracked so the 'no sugary drinks / sugar' habit shows up honestly.",
    },
    {
        "name": "Honey",
        "kcal_per_100g": "304.00", "protein_g": "0.30", "fat_g": "0.00",
        "carb_g": "82.00", "satiety_index": 70,
        "common_unit": "1 tablespoon = 21g",
        "default_grams": "21.00",
        "notes": "Sugar source, just slightly lower glycaemic than table sugar.",
    },
    {
        "name": "Mayonnaise",
        "kcal_per_100g": "680.00", "protein_g": "1.00", "fat_g": "75.00",
        "carb_g": "0.60", "satiety_index": 80,
        "common_unit": "1 tablespoon = 14g",
        "default_grams": "14.00",
        "notes": "Hidden-calorie sauce. Track when used.",
    },
    {
        "name": "Margarine",
        "kcal_per_100g": "717.00", "protein_g": "0.20", "fat_g": "81.00",
        "carb_g": "0.70", "satiety_index": 80,
        "common_unit": "1 tablespoon = 14g",
        "default_grams": "14.00",
        "notes": "Almost identical kcal to butter — same caution applies.",
    },
    # ---- Drinks (for honest tracking of habit booleans) -------------
    {
        "name": "Coca-Cola",
        "kcal_per_100g": "42.00", "protein_g": "0.00", "fat_g": "0.00",
        "carb_g": "11.00", "satiety_index": 30,
        "common_unit": "1 can = 330g",
        "default_grams": "330.00",
        "notes": "Per 100 ml. Each can ≈ 140 kcal of pure sugar. Trips the 'no sugary drinks' habit.",
    },
    {
        "name": "Castle Lager beer",
        "kcal_per_100g": "41.00", "protein_g": "0.40", "fat_g": "0.00",
        "carb_g": "3.10", "satiety_index": 50,
        "common_unit": "1 bottle = 340g",
        "default_grams": "340.00",
        "notes": "Per 100 ml. Each 340 ml ≈ 140 kcal. Trips the 'no alcohol' habit.",
    },
    {
        "name": "Red wine, dry",
        "kcal_per_100g": "85.00", "protein_g": "0.10", "fat_g": "0.00",
        "carb_g": "2.60", "satiety_index": 50,
        "common_unit": "1 glass = 150g",
        "default_grams": "150.00",
        "notes": "Per 100 ml. Each 150 ml glass ≈ 128 kcal. Trips the 'no alcohol' habit.",
    },
    {
        "name": "Mahewu",
        "kcal_per_100g": "32.00", "protein_g": "1.00", "fat_g": "0.10",
        "carb_g": "6.50", "satiety_index": 110,
        "common_unit": "1 cup = 250g",
        "default_grams": "250.00",
        "notes": "Per 100 ml. Fermented maize drink; sugar varies — pick unsweetened if possible.",
    },
]


def populate(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    FoodItem = apps.get_model("tracker", "FoodItem")
    for spec in FOOD_ITEMS:
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


def unpopulate(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    FoodItem = apps.get_model("tracker", "FoodItem")
    FoodItem.objects.filter(name__in=[spec["name"] for spec in FOOD_ITEMS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0008_seed_meal_templates"),
    ]

    operations = [
        migrations.RunPython(populate, reverse_code=unpopulate),
    ]
