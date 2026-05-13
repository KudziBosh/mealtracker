"""Closeout-ritual helpers.

The "closeout" is the deliberate evening pass over today's habits, walking,
notes, and (optionally) weight. It's the protocol's adherence anchor — much
stronger than dashboard habit taps because it implies the user actively
reviewed the day rather than half-ticking things in passing.

This module owns the pure-function logic so it can be shared by:

* the closeout view (``tracker.views.closeout``),
* the eventual Telegram bot's "you haven't closed out today" reminder,
* the Celery beat job that produces the Sunday weekly summary,
* the DRF API once a ``/api/closeout/`` endpoint lands.

Everything here is side-effect-free and Decimal-clean. No queries; callers
load ``DailyLog`` / ``MealEntry`` themselves and pass what's needed.
"""

from __future__ import annotations

from decimal import Decimal

from . import protocol
from .models import DailyLog


def closeout_suggestions(
    *,
    daily_log: DailyLog | None,
    totals: dict[str, Decimal],
) -> dict[str, bool]:
    """Suggest habit states from logged data without overwriting saved choices.

    Only habits we can infer from *meal data alone* are surfaced as fresh-day
    suggestions:

    * ``hit_protein`` and ``under_calories`` follow directly from logged
      ``MealEntry`` totals.
    * ``ate_breakfast`` and ``no_alcohol_or_sugar`` only echo what's already
      saved on the ``DailyLog`` — they can't be inferred from food rows.

    ``walked_30`` is deliberately excluded: the only surface that writes
    ``walked_minutes`` is the closeout itself, so suggesting from it would be
    circular ("we suggest walked_30=True because you previously said so").
    Once the dashboard grows a walking-minutes input, this can come back.
    """
    return {
        "hit_protein": totals["protein_g"] >= Decimal(protocol.DAILY_PROTEIN_G),
        "under_calories": (
            totals["kcal"] >= Decimal(protocol.DAILY_KCAL_FLOOR)
            and totals["kcal"] <= Decimal(protocol.DAILY_KCAL_TARGET)
        ),
        "ate_breakfast": bool(daily_log and daily_log.ate_breakfast),
        "no_alcohol_or_sugar": bool(daily_log and daily_log.no_alcohol_or_sugar),
    }


def closeout_initial(
    *,
    daily_log: DailyLog | None,
    suggestions: dict[str, bool],
) -> dict[str, object]:
    """Initial form data: saved values win; suggestions only fill new logs.

    Returns an empty dict when ``daily_log`` already exists — Django's
    ``ModelForm(instance=...)`` will then populate every field from the
    saved row. Only on a totally cold day (no taps yet, no walking data,
    nothing) do we seed with the protocol-inferred suggestions.
    """
    if daily_log is not None:
        return {}
    return {
        **suggestions,
        "walked_minutes": 0,
        "steps": None,
        "notes": "",
    }


def closeout_habit_rows(
    *,
    form,
    suggestions: dict[str, bool],
    has_saved_log: bool,
) -> list[dict[str, object]]:
    """Pair each habit checkbox with its protocol label and suggestion.

    Habits that we can't infer from meal data (currently ``walked_30``) fall
    through to ``suggested=False`` so the template's pill simply doesn't
    render — the user picks the value themselves at closeout time.
    """
    return [
        {
            "field": field,
            "label": label,
            "bound_field": form[field],
            "suggested": suggestions.get(field, False),
            "has_saved_log": has_saved_log,
        }
        for field, label in protocol.HABIT_LABELS
    ]
