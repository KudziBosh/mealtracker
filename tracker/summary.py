"""Progress summary helpers for dashboard and end-of-day views."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Model
from django.utils import timezone

from tracker import protocol
from tracker.models import DailyLog, MealEntry, WeightEntry


def two_decimals(value: Decimal) -> Decimal:
    """Return a stable two-decimal value for macro display."""
    return value.quantize(Decimal("0.01"))


def meal_totals(meals: list) -> dict[str, Decimal]:
    """Calculate running macro totals for meal entries."""
    totals = {
        "kcal": Decimal("0"),
        "protein_g": Decimal("0"),
        "fat_g": Decimal("0"),
        "carb_g": Decimal("0"),
    }
    for meal in meals:
        totals["kcal"] += meal.kcal
        totals["protein_g"] += meal.protein_g
        totals["fat_g"] += meal.fat_g
        totals["carb_g"] += meal.carb_g
    return {key: two_decimals(value) for key, value in totals.items()}


def build_end_of_day_summary(
    *,
    summary_date: date,
    daily_log: DailyLog | None,
    totals: dict[str, Decimal],
    latest_weight: WeightEntry | None,
) -> dict[str, object]:
    """Assess the day against the plan's non-negotiables and key habits."""
    kcal = totals["kcal"]
    protein = totals["protein_g"]
    kcal_target = Decimal(protocol.DAILY_KCAL_TARGET)
    kcal_floor = Decimal(protocol.DAILY_KCAL_FLOOR)
    protein_target = Decimal(protocol.DAILY_PROTEIN_G)

    protein_hit = protein >= protein_target
    calories_under_target = kcal <= kcal_target
    calories_above_floor = kcal >= kcal_floor
    calories_in_range = calories_above_floor and calories_under_target
    habits_completed = daily_log.habits_completed if daily_log else 0
    habits_total = len(protocol.HABIT_LABELS)
    walked_minutes = daily_log.walked_minutes if daily_log else 0
    walked_target_hit = walked_minutes >= protocol.WALKING_HABIT_THRESHOLD_MIN
    weigh_in_due = summary_date.weekday() == protocol.WEIGH_IN_DAY
    weighed_today = bool(latest_weight and latest_weight.date == summary_date)

    checks = [
        {
            "label": "Protein",
            "value": f"{protein:.0f} / {protocol.DAILY_PROTEIN_G} g",
            "status": "hit" if protein_hit else "miss",
            "message": (
                "Target hit" if protein_hit else "Prioritise lean protein before adding carbs/fats."
            ),
        },
        {
            "label": "Calories",
            "value": f"{kcal:.0f} / {protocol.DAILY_KCAL_TARGET} kcal",
            "status": "hit" if calories_in_range else "warn",
            "message": (
                "Within the planned range"
                if calories_in_range
                else (
                    "Below the 1800 kcal floor"
                    if not calories_above_floor
                    else "Above the 2000 kcal target"
                )
            ),
        },
        {
            "label": "Habits",
            "value": f"{habits_completed} / {habits_total}",
            "status": "hit" if habits_completed >= 4 else "warn",
            "message": (
                "Strong adherence day"
                if habits_completed >= 4
                else "Close the remaining habit gaps."
            ),
        },
        {
            "label": "Walking",
            "value": f"{walked_minutes} min",
            "status": "hit" if walked_target_hit else "miss",
            "message": (
                "30+ minute habit done"
                if walked_target_hit
                else "Add a walk before bed if possible."
            ),
        },
        {
            "label": "Weigh-in",
            "value": latest_weight.weight_kg if latest_weight else "No entry",
            "status": "hit" if not weigh_in_due or weighed_today else "warn",
            "message": (
                "Logged today"
                if weighed_today
                else "Due today" if weigh_in_due else "Next due Tuesday"
            ),
        },
    ]

    hit_count = sum(1 for check in checks if check["status"] == "hit")
    blockers = [check for check in checks if check["status"] == "miss"]
    warnings = [check for check in checks if check["status"] == "warn"]
    on_track = protein_hit and calories_under_target and habits_completed >= 4 and walked_target_hit

    if on_track:
        headline = "On track today"
        nudge = "This is the pattern the plan is built around: protein, calories, walking, and consistency."
    elif blockers:
        headline = "Needs attention before bed"
        nudge = blockers[0]["message"]
    elif warnings:
        headline = "Mostly on track"
        nudge = warnings[0]["message"]
    else:
        headline = "Log more data"
        nudge = "Add meals and habit ticks to get a clearer read."

    return {
        "headline": headline,
        "nudge": nudge,
        "on_track": on_track,
        "hit_count": hit_count,
        "total_count": len(checks),
        "checks": checks,
    }


# ---- Comprehensive end-of-day review --------------------------------------


def _pct(actual: Decimal, target: Decimal) -> int:
    """Return ``actual / target`` as an int percentage, capped at 200."""
    if target <= 0:
        return 0
    return min(int((actual / target) * 100), 200)


def _macro_row(
    label: str,
    actual: Decimal,
    target: int,
    unit: str,
    *,
    is_non_negotiable: bool = False,
) -> dict[str, object]:
    """Build a single macro display row with target/actual/remaining + status."""
    target_d = Decimal(target)
    remaining = max(target_d - actual, Decimal("0"))
    over = max(actual - target_d, Decimal("0"))
    pct = _pct(actual, target_d)
    # For protein the goal is hit-or-exceed; for kcal/fat/carbs the goal is
    # roughly-meet (within ±10% counts as on-target).
    if is_non_negotiable:
        status = "hit" if actual >= target_d else "miss"
    else:
        status = (
            "hit" if 90 <= pct <= 110 else "warn" if 75 <= pct < 90 or 110 < pct <= 125 else "miss"
        )
    return {
        "label": label,
        "actual": actual,
        "target": target,
        "unit": unit,
        "pct": pct,
        "remaining": remaining,
        "over": over,
        "status": status,
        "is_non_negotiable": is_non_negotiable,
    }


def _satiety_summary(meals: list[MealEntry]) -> dict[str, object]:
    """Gram-weighted average Holt satiety score for the day's meals.

    Skips foods with no satiety value; Holt's 1995 baseline is ``white bread =
    100``, so anything below 100 is a "leakage" signal worth surfacing.
    """
    weighted_sum = Decimal("0")
    weight_total = Decimal("0")
    leakage_items: list[tuple[str, int]] = []
    high_satiety_items: list[tuple[str, int]] = []

    for meal in meals:
        score = meal.food.satiety_index
        if score is None:
            continue
        score_d = Decimal(score)
        weighted_sum += score_d * meal.grams
        weight_total += meal.grams
        if score < 100:
            leakage_items.append((meal.food.name, score))
        elif score >= 200:
            high_satiety_items.append((meal.food.name, score))

    if weight_total == 0:
        return {
            "available": False,
            "average": None,
            "baseline": 100,
            "leakage_items": [],
            "high_satiety_items": [],
            "message": "No satiety data on today's foods yet.",
        }

    avg = int((weighted_sum / weight_total).quantize(Decimal("1")))
    if avg >= 200:
        message = "Excellent — meals were high-satiety, which keeps hunger in check between feeds."
    elif avg >= 150:
        message = "Solid satiety. Most calories came from foods that hold fullness."
    elif avg >= 100:
        message = "At the Holt baseline. Lean harder on potato, fish, eggs, and fruit tomorrow."
    else:
        message = "Below the Holt baseline — most calories were from low-satiety foods. Expect hunger to climb."

    return {
        "available": True,
        "average": avg,
        "baseline": 100,
        "leakage_items": leakage_items,
        "high_satiety_items": high_satiety_items,
        "message": message,
    }


def _walking_summary(
    daily_log: DailyLog | None,
    protocol_week_num: int,
) -> dict[str, object]:
    """Walking minutes today vs the protocol-week target (30 → 75 min buildup)."""
    walked = daily_log.walked_minutes if daily_log else 0
    steps = daily_log.steps if daily_log else None
    target = protocol.target_walking_minutes(protocol_week_num)
    threshold_hit = walked >= protocol.WALKING_HABIT_THRESHOLD_MIN
    target_hit = walked >= target

    if target_hit:
        status = "hit"
        message = f"Met the week-{protocol_week_num} target of {target} min."
    elif threshold_hit:
        status = "warn"
        message = f"Past the {protocol.WALKING_HABIT_THRESHOLD_MIN}-min habit, but short of the {target}-min target for week {protocol_week_num}."
    else:
        status = "miss"
        message = f"Below {protocol.WALKING_HABIT_THRESHOLD_MIN}-min minimum. Target is {target} min for week {protocol_week_num}."

    return {
        "walked_minutes": walked,
        "steps": steps,
        "target_minutes": target,
        "threshold_minutes": protocol.WALKING_HABIT_THRESHOLD_MIN,
        "threshold_hit": threshold_hit,
        "target_hit": target_hit,
        "status": status,
        "message": message,
    }


def _weight_pace(
    *,
    on_date: date,
    latest_weight: WeightEntry | None,
    weights: list[WeightEntry],
) -> dict[str, object]:
    """Compare current weight + recent loss rate to the 9–14 month plan window."""
    if latest_weight is None:
        return {
            "available": False,
            "message": "No weigh-in yet. Step on the scale on Tuesday to start the trend.",
            "latest_kg": None,
            "delta_total_kg": None,
            "delta_last_week_kg": None,
            "kg_to_goal": None,
            "weeks_to_goal_min": protocol.PLAN_DURATION_WEEKS_MIN,
            "weeks_to_goal_max": protocol.PLAN_DURATION_WEEKS_MAX,
            "required_kg_per_week_min": None,
            "required_kg_per_week_max": None,
            "actual_kg_per_week_last_4w": None,
            "on_pace": None,
            "days_since_last_weigh_in": None,
        }

    current = latest_weight.weight_kg
    start = Decimal(protocol.START_WEIGHT_KG)
    goal = Decimal(protocol.GOAL_WEIGHT_KG)
    delta_total = current - start
    kg_to_goal = current - goal
    days_since = (on_date - latest_weight.date).days

    # Required loss rate to land between the 9- and 14-month bounds.
    required_min = (
        (kg_to_goal / protocol.PLAN_DURATION_WEEKS_MAX) if kg_to_goal > 0 else Decimal("0")
    )
    required_max = (
        (kg_to_goal / protocol.PLAN_DURATION_WEEKS_MIN) if kg_to_goal > 0 else Decimal("0")
    )

    # Actual rate: weights ≥ 28 days old give the most stable 4-week average.
    four_weeks_ago = on_date - timedelta(days=28)
    older = [w for w in weights if w.date <= four_weeks_ago]
    if older:
        baseline = older[-1]
        weeks_span = max(Decimal((on_date - baseline.date).days) / Decimal("7"), Decimal("0.1"))
        actual_per_week = (current - baseline.weight_kg) / weeks_span
    elif weights and weights[0].date < on_date:
        # Fall back to the earliest available weight to give *some* signal.
        baseline = weights[0]
        weeks_span = max(Decimal((on_date - baseline.date).days) / Decimal("7"), Decimal("0.1"))
        actual_per_week = (current - baseline.weight_kg) / weeks_span
    else:
        actual_per_week = None

    delta_last_week = None
    if weights:
        week_ago = on_date - timedelta(days=7)
        prior = [w for w in weights if w.date <= week_ago]
        if prior:
            delta_last_week = current - prior[-1].weight_kg

    on_pace: bool | None
    if actual_per_week is None or kg_to_goal <= 0:
        on_pace = None
        message = (
            "Goal already reached — maintenance mode."
            if kg_to_goal <= 0
            else "Not enough weigh-ins yet to read a trend."
        )
    elif actual_per_week <= -required_min:
        on_pace = True
        message = f"Losing {-actual_per_week:.2f} kg/week — inside the 9–14 month plan window."
    elif actual_per_week < 0:
        on_pace = False
        message = (
            f"Losing {-actual_per_week:.2f} kg/week — below the {required_min:.2f} kg/week "
            "minimum to land by month 14."
        )
    else:
        on_pace = False
        message = f"Trend is flat or rising ({actual_per_week:+.2f} kg/week). Tighten calories and protein."

    return {
        "available": True,
        "message": message,
        "latest_kg": current,
        "latest_date": latest_weight.date,
        "delta_total_kg": delta_total,
        "delta_last_week_kg": delta_last_week,
        "kg_to_goal": kg_to_goal,
        "weeks_to_goal_min": protocol.PLAN_DURATION_WEEKS_MIN,
        "weeks_to_goal_max": protocol.PLAN_DURATION_WEEKS_MAX,
        "required_kg_per_week_min": required_min,
        "required_kg_per_week_max": required_max,
        "actual_kg_per_week_last_4w": actual_per_week,
        "on_pace": on_pace,
        "days_since_last_weigh_in": days_since,
    }


def _week_to_date(user: Model, on_date: date) -> dict[str, object]:
    """Monday-to-``on_date`` aggregate: habits hit, walking minutes, weight delta.

    ``habits_pct`` is intentionally a *slot-level* metric:
    ``ticked_habits / (days_elapsed * 5)``. A day where the user ticked 3
    habits in the morning but never closed out still counts toward the
    numerator and the denominator. This is the right reading for an
    in-progress week — it answers "how is the user tracking against the
    habit grid right now", not "how many days were ritualised".

    The "did the user close out" question is answered separately by the
    closeout streak + the weekday/weekend adherence band on
    ``consistency``. The two metrics will sometimes disagree (e.g. lots of
    taps but no closeouts → high habits_pct, low streak) — that's by design.
    """
    week_start = on_date - timedelta(days=on_date.weekday())
    logs = list(
        DailyLog.objects.filter(user=user, date__range=(week_start, on_date)).order_by("date")
    )
    weights = list(
        WeightEntry.objects.filter(user=user, date__range=(week_start, on_date)).order_by("date")
    )

    days_so_far = (on_date - week_start).days + 1
    habits_hit = sum(log.habits_completed for log in logs)
    habits_possible = days_so_far * len(protocol.HABIT_LABELS)
    walking_minutes = sum(log.walked_minutes for log in logs)
    days_walked = sum(1 for log in logs if log.walked_minutes > 0)
    pct = round((habits_hit / habits_possible) * 100) if habits_possible else 0
    weight_delta = weights[-1].weight_kg - weights[0].weight_kg if len(weights) >= 2 else None

    return {
        "week_start": week_start,
        "days_so_far": days_so_far,
        "habits_hit": habits_hit,
        "habits_possible": habits_possible,
        "habits_pct": pct,
        "walking_total_minutes": walking_minutes,
        "days_walked": days_walked,
        "weight_delta_kg": weight_delta,
        "weight_count": len(weights),
    }


def _closeout_streak(user: Model, on_date: date) -> int:
    """Count consecutive days up to ``on_date`` with a completed closeout.

    Pulls only the dates that *have* a non-null ``closed_at`` into a set, then
    walks backwards from ``on_date`` until the first gap. For a 9–14 month
    plan the membership query stays trivially small and the loop short-
    circuits on the first missing day.
    """
    closed_dates: set[date] = set(
        DailyLog.objects.filter(
            user=user,
            date__lte=on_date,
            closed_at__isnull=False,
        ).values_list("date", flat=True)
    )
    streak = 0
    cursor = on_date
    while cursor in closed_dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def _weekday_weekend_adherence(user: Model, on_date: date) -> dict[str, object]:
    """Compare last 28 days weekday vs weekend habit completion.

    Window is a **rolling 28 calendar days** ending on ``on_date`` — deliberately
    not aligned to protocol weeks. The point of this metric is to surface the
    one pattern the meal-plan doc calls out by name (weekend regression), and
    a 4-week smoothing window is the natural granularity for that. It will
    occasionally disagree at the edges with the protocol-week numbers shown
    elsewhere on the summary; that's expected.
    """
    start = on_date - timedelta(days=27)
    logs = list(DailyLog.objects.filter(user=user, date__range=(start, on_date)))
    buckets = {
        "weekday": {"hit": 0, "possible": 0},
        "weekend": {"hit": 0, "possible": 0},
    }
    for log in logs:
        bucket = "weekend" if log.date.weekday() >= 5 else "weekday"
        buckets[bucket]["hit"] += log.habits_completed
        buckets[bucket]["possible"] += log.habits_total

    def pct(bucket: dict[str, int]) -> int | None:
        if bucket["possible"] == 0:
            return None
        return round(bucket["hit"] / bucket["possible"] * 100)

    weekday_pct = pct(buckets["weekday"])
    weekend_pct = pct(buckets["weekend"])
    weekend_gap = (
        weekday_pct - weekend_pct if weekday_pct is not None and weekend_pct is not None else None
    )

    if weekend_gap is not None and weekend_gap >= 20:
        message = "Weekend adherence is the current risk pattern."
        weekend_drop_risk = True
    elif weekend_pct is not None:
        message = "Weekend adherence is broadly in line with weekdays."
        weekend_drop_risk = False
    else:
        message = "Log a full weekend to compare consistency."
        weekend_drop_risk = False

    return {
        "start": start,
        "end": on_date,
        "weekday_pct": weekday_pct,
        "weekend_pct": weekend_pct,
        "weekend_gap": weekend_gap,
        "weekend_drop_risk": weekend_drop_risk,
        "message": message,
    }


def build_progress_summary(user: Model, on_date: date) -> dict[str, object]:
    """Comprehensive end-of-day read against the plan.

    Returns a dict with ``date``, ``protocol_week``, ``days_in_plan``, four
    ``macros`` rows, ``habits`` block, ``walking``, ``satiety``, ``weight``
    (pace + deltas), ``week_to_date``, plus a single-sentence ``verdict``.

    Pure function with respect to template rendering — template can iterate
    rows without further computation.
    """
    daily_log = DailyLog.objects.filter(user=user, date=on_date).first()
    meals = list(MealEntry.objects.filter(user=user, eaten_at__date=on_date).select_related("food"))
    weights_all = list(WeightEntry.objects.filter(user=user).order_by("date"))
    latest_weight = (
        WeightEntry.objects.filter(user=user, date__lte=on_date).order_by("-date").first()
    )
    first_weight_date = weights_all[0].date if weights_all else None
    week_num = protocol.protocol_week(first_weight_date, on_date)
    days_in_plan = (on_date - first_weight_date).days + 1 if first_weight_date is not None else None

    totals = meal_totals(meals)
    macros = [
        _macro_row(
            "Calories",
            totals["kcal"],
            protocol.DAILY_KCAL_TARGET,
            "kcal",
        ),
        _macro_row(
            "Protein",
            totals["protein_g"],
            protocol.DAILY_PROTEIN_G,
            "g",
            is_non_negotiable=True,
        ),
        _macro_row("Fat", totals["fat_g"], protocol.DAILY_FAT_G, "g"),
        _macro_row("Carbs", totals["carb_g"], protocol.DAILY_CARB_G, "g"),
    ]

    # Kcal floor is a separate concern from the over/under target — flag it
    # explicitly. The plan says "don't drop below this regardless".
    kcal_floor_breached = totals["kcal"] > 0 and totals["kcal"] < protocol.DAILY_KCAL_FLOOR

    habits = {
        "completed": daily_log.habits_completed if daily_log else 0,
        "total": len(protocol.HABIT_LABELS),
        "rows": [
            {
                "field": field,
                "label": label,
                "done": bool(daily_log and getattr(daily_log, field)),
            }
            for field, label in protocol.HABIT_LABELS
        ],
        "notes": daily_log.notes if daily_log else "",
    }

    walking = _walking_summary(daily_log, week_num)
    satiety = _satiety_summary(meals)
    weight = _weight_pace(on_date=on_date, latest_weight=latest_weight, weights=weights_all)
    week_to_date = _week_to_date(user, on_date)
    consistency = {
        "closeout_streak": _closeout_streak(user, on_date),
        "weekday_weekend": _weekday_weekend_adherence(user, on_date),
    }

    # Verdict: protein hit + kcal in range + walking target + 4/5 habits ⇒ ✅.
    protein_hit = macros[1]["status"] == "hit"
    kcal_in_range = macros[0]["status"] in {"hit", "warn"} and not kcal_floor_breached
    walking_hit = walking["target_hit"]
    habits_strong = habits["completed"] >= 4
    on_track = protein_hit and kcal_in_range and walking_hit and habits_strong

    if kcal_floor_breached:
        verdict = "Below the 1800 kcal floor — eat more. Persistent under-eating sabotages protein and sleep."
        verdict_level = "miss"
    elif on_track:
        verdict = "On the protocol today. This is the pattern that compounds."
        verdict_level = "hit"
    elif not protein_hit:
        verdict = f"Protein short ({macros[1]['actual']:.0f}/{macros[1]['target']} g). The one non-negotiable."
        verdict_level = "miss"
    elif not walking_hit:
        verdict = walking["message"]
        verdict_level = walking["status"]
    elif not habits_strong:
        verdict = (
            f"Habits at {habits['completed']}/{habits['total']}. Close the easy gaps before bed."
        )
        verdict_level = "warn"
    else:
        verdict = "Mostly there — finish the day clean."
        verdict_level = "warn"

    # Closeout state: surface ``closed_at`` for the badge, and a derived
    # ``days_late`` / ``closeout_window_open`` pair so the template knows
    # whether to show a working CTA on past dates. Future dates fall outside
    # the window by definition.
    today = timezone.localdate()
    days_late = (today - on_date).days
    closeout_window_open = 0 <= days_late <= protocol.CLOSEOUT_LATE_DAYS_MAX

    return {
        "date": on_date,
        "protocol_week": week_num,
        "days_in_plan": days_in_plan,
        "macros": macros,
        "kcal_floor": protocol.DAILY_KCAL_FLOOR,
        "kcal_floor_breached": kcal_floor_breached,
        "habits": habits,
        "walking": walking,
        "satiety": satiety,
        "weight": weight,
        "week_to_date": week_to_date,
        "consistency": consistency,
        "verdict": verdict,
        "verdict_level": verdict_level,
        "on_track": on_track,
        "meals": meals,
        "totals": totals,
        "closed_at": daily_log.closed_at if daily_log else None,
        "days_late": days_late,
        "closeout_window_open": closeout_window_open,
    }
