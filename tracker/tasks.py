"""Celery tasks: scheduled Telegram notifications."""

import asyncio
import logging
from datetime import date, timedelta

from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


def _bot_and_chat():
    """Return (Bot, chat_id) or (None, None) if Telegram is not configured."""
    from telegram import Bot

    from tracker.models import TelegramSettings

    ts = TelegramSettings.load()
    token = settings.TELEGRAM_BOT_TOKEN
    if not token or not ts.chat_id:
        logger.warning("Telegram not configured; skipping notification.")
        return None, None
    return Bot(token=token), ts.chat_id


def _owner():
    from django.contrib.auth import get_user_model

    return get_user_model().objects.filter(is_superuser=True).first()


def _send(bot, chat_id: str, text: str, **kwargs) -> None:
    asyncio.run(bot.send_message(chat_id=chat_id, text=text, **kwargs))


@shared_task(bind=True, max_retries=3)
def send_morning_ping(self) -> None:
    """Daily 07:00 — targets message; Tuesday adds weigh-in reminder."""
    from tracker import protocol

    bot, chat_id = _bot_and_chat()
    if not bot:
        return

    today = date.today()
    if today.weekday() == protocol.WEIGH_IN_DAY:
        text = (
            "Tuesday weigh-in day. Step on the scale before food, after the toilet. "
            "Reply with /weigh <kg>."
        )
    else:
        text = (
            f"Good morning. Today's targets: {protocol.DAILY_KCAL_TARGET} kcal, "
            f"{protocol.DAILY_PROTEIN_G} g protein. Walk 30+ min. Don't skip breakfast."
        )

    try:
        _send(bot, chat_id, text)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)  # noqa: B904


@shared_task(bind=True, max_retries=3)
def send_evening_habit_check(self) -> None:
    """Daily 21:00 — inline keyboard with the five habit toggles."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    from tracker import protocol
    from tracker.models import DailyLog

    bot, chat_id = _bot_and_chat()
    if not bot:
        return

    owner = _owner()
    log = DailyLog.objects.filter(user=owner, date=date.today()).first() if owner else None

    buttons = []
    for field, label in protocol.HABIT_LABELS:
        done = bool(log and getattr(log, field))
        tick = "✓ " if done else "☐ "
        buttons.append(
            [InlineKeyboardButton(text=f"{tick}{label}", callback_data=f"habit:{field}")]
        )

    try:
        _send(
            bot,
            chat_id,
            "Habit check for today. Tap to toggle:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)  # noqa: B904


@shared_task(bind=True, max_retries=3)
def send_weekly_summary(self) -> None:
    """Sunday 19:00 — weight delta, habit %, walking total."""
    from tracker.models import DailyLog, WeightEntry

    bot, chat_id = _bot_and_chat()
    if not bot:
        return

    owner = _owner()
    if not owner:
        return

    today = date.today()
    week_start = today - timedelta(days=6)

    weights = list(
        WeightEntry.objects.filter(user=owner, date__range=[week_start, today]).order_by("date")
    )
    if len(weights) >= 2:
        delta = weights[-1].weight_kg - weights[0].weight_kg
        weight_line = f"Weight: {weights[0].weight_kg} → {weights[-1].weight_kg} ({delta:+.1f} kg)"
    elif weights:
        weight_line = f"Weight: {weights[-1].weight_kg} kg (one entry this week)"
    else:
        weight_line = "Weight: no entries this week"

    logs = list(DailyLog.objects.filter(user=owner, date__range=[week_start, today]))
    hit = sum(log.habits_completed for log in logs)
    pct = round(hit / 35 * 100)
    total_min = sum(log.walked_minutes for log in logs)
    days_walked = sum(1 for log in logs if log.walked_minutes > 0)

    first_entry = WeightEntry.objects.filter(user=owner).order_by("date").first()
    if first_entry:
        first_monday = first_entry.date - timedelta(days=first_entry.date.weekday())
        week_n = max(1, (week_start - first_monday).days // 7 + 1)
    else:
        week_n = 1

    text = (
        f"Week {week_n} done.\n"
        f"{weight_line}\n"
        f"Habits: {pct}% ({hit}/35)\n"
        f"Walking: {total_min} min across {days_walked}/7 days\n"
        f"{_nudge(logs)}"
    )

    try:
        _send(bot, chat_id, text)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)  # noqa: B904


def _nudge(logs: list) -> str:
    """Return a research-grounded nudge based on the week's habit data."""
    if not logs:
        return "Start logging tomorrow. Consistency compounds."

    weekday_logs = [entry for entry in logs if entry.date.weekday() < 5]
    weekend_logs = [entry for entry in logs if entry.date.weekday() >= 5]

    if weekday_logs and weekend_logs:
        wd_rate = sum(entry.habits_completed for entry in weekday_logs) / (len(weekday_logs) * 5)
        we_rate = sum(entry.habits_completed for entry in weekend_logs) / (len(weekend_logs) * 5)
        if we_rate < wd_rate - 0.2:
            return "Weekend habits dropped. NWCR data shows weekends are where long-term results are won or lost."

    avg = sum(entry.habits_completed for entry in logs) / len(logs)
    if avg >= 4:
        return "Strong week. This consistency is exactly what predicts sustained weight loss."
    if avg >= 3:
        return "Solid base. One or two more consistent habits next week will compound."
    return "Rough week. Pick one habit to nail every day — let the others follow."
