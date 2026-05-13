"""
Protocol constants — the hardcoded numbers from the meal plan document.

These are owner-specific. Do not generalise into runtime-configurable settings;
keeping them hardcoded is intentional (see CLAUDE.md). If a number changes, edit
this file and add a test that asserts the new value.
"""

from datetime import date, time, timedelta

# ---- Weight ---------------------------------------------------------------

START_WEIGHT_KG = 120
GOAL_WEIGHT_KG = 90

# Acceptable bounds for any weigh-in. Owner-specific but generous on both
# sides so an accidental scale error (e.g. an empty 0.0 read or a stray
# decimal place) gets caught by the model + form validators rather than
# polluting the trend. Shared between WeightEntry model validators and the
# closeout's CloseoutWeightForm so they can't drift apart.
WEIGHT_KG_MIN = 30
WEIGHT_KG_MAX = 600

# Plan duration window from CLAUDE.md: 9–14 months for the 30 kg drop. Used to
# bound the "are you on pace?" check on the end-of-day summary.
PLAN_DURATION_WEEKS_MIN = 9 * 4  # 36 weeks ≈ 9 months
PLAN_DURATION_WEEKS_MAX = 14 * 4  # 56 weeks ≈ 14 months


# ---- Daily macro targets --------------------------------------------------

DAILY_KCAL_TARGET = 2000
DAILY_KCAL_FLOOR = 1800  # don't go below this regardless

# Per the plan doc, only protein is non-negotiable; fat and carbs are flexible
# starting splits. The dashboard uses these flags to drive visual hierarchy.
DAILY_PROTEIN_G = 190
DAILY_FAT_G = 60
DAILY_CARB_G = 165
PROTEIN_IS_NON_NEGOTIABLE = True


# ---- Walking --------------------------------------------------------------

# 8-week buildup from the plan: 30 → 75 min. Returns target minutes/day given a
# 1-indexed protocol week.
WALKING_BUILDUP_MIN = {
    1: 30,
    2: 30,
    3: 45,
    4: 45,
    5: 60,
    6: 60,
    7: 75,  # week 7+ steady state
}
WALKING_STEADY_STATE_MIN = 75
WALKING_HABIT_THRESHOLD_MIN = 30  # the "walked 30+" boolean trips at this


def target_walking_minutes(protocol_week: int) -> int:
    """Return the target walking minutes/day for the given protocol week."""
    if protocol_week < 1:
        return WALKING_BUILDUP_MIN[1]
    return WALKING_BUILDUP_MIN.get(protocol_week, WALKING_STEADY_STATE_MIN)


# ---- Protocol week / plan timeline ----------------------------------------


def protocol_week(first_weight_date: date | None, on_date: date) -> int:
    """Return the 1-indexed protocol week for ``on_date``.

    Per CLAUDE.md ("Week 1" is the first Monday on or after the first
    ``WeightEntry``). Returns 1 if there's no first weight yet, or if
    ``on_date`` falls before that Monday — keeps callers from having to
    special-case the cold-start case.
    """
    if first_weight_date is None:
        return 1
    first_monday = first_weight_date - timedelta(days=first_weight_date.weekday())
    days = (on_date - first_monday).days
    if days < 0:
        return 1
    return days // 7 + 1


# ---- Weigh-in ------------------------------------------------------------

# Monday=0 ... Sunday=6 — matches Python's datetime.weekday()
WEIGH_IN_DAY = 1  # Tuesday

# Default Telegram ping times (the model overrides per-instance, but these are
# the protocol-aligned defaults for new TelegramSettings rows).
DEFAULT_MORNING_PING = time(7, 0)
DEFAULT_EVENING_PING = time(21, 0)
DEFAULT_WEEKLY_SUMMARY_DAY = 6  # Sunday
DEFAULT_WEEKLY_SUMMARY_TIME = time(19, 0)


# ---- Habit display labels -------------------------------------------------

# Field name on DailyLog → human-readable label exactly as worded in the plan
# document. Used by templates and any future bot copy. Order matters — this is
# how the tracker grid in the plan doc reads top to bottom.
HABIT_LABELS = (
    ("hit_protein", "Hit protein target (190 g)"),
    ("under_calories", "Stayed within calories (2000)"),
    ("walked_30", "Walked 30+ minutes"),
    ("ate_breakfast", "Ate breakfast"),
    ("no_alcohol_or_sugar", "No sugary drinks / alcohol"),
)
