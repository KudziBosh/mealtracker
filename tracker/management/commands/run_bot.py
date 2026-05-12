"""Management command: run the Telegram bot (long-polling loop)."""

import logging
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from tracker import protocol
from tracker.models import DailyLog, FoodItem, MealEntry, TelegramSettings, WeightEntry

logger = logging.getLogger(__name__)


def _owner():
    return get_user_model().objects.filter(is_superuser=True).first()


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start — bind this chat ID to TelegramSettings."""
    chat_id = str(update.effective_chat.id)
    ts, _ = await TelegramSettings.objects.aget_or_create(pk=1)
    ts.chat_id = chat_id
    ts.pk = 1
    await ts.asave()
    await update.message.reply_text(
        f"Mealtracker connected. Chat ID {chat_id} saved.\n"
        "Commands: /today  /weigh <kg>  /log <food> <grams>"
    )


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/today — running macro totals for today."""
    from asgiref.sync import sync_to_async

    owner = await sync_to_async(_owner)()
    if not owner:
        await update.message.reply_text("No owner account found.")
        return

    today = timezone.localdate()
    meals = await sync_to_async(
        lambda: list(
            MealEntry.objects.filter(user=owner, eaten_at__date=today).select_related("food")
        )
    )()

    kcal = sum(m.kcal for m in meals)
    protein = sum(m.protein_g for m in meals)

    log = await DailyLog.objects.filter(user=owner, date=today).afirst()
    habits_done = log.habits_completed if log else 0

    text = (
        f"Today — {today}\n"
        f"Calories: {kcal:.0f} / {protocol.DAILY_KCAL_TARGET}\n"
        f"Protein:  {protein:.0f} g / {protocol.DAILY_PROTEIN_G} g\n"
        f"Habits:   {habits_done}/5"
    )
    await update.message.reply_text(text)


async def cmd_weigh(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/weigh <kg> — log today's weight."""
    from asgiref.sync import sync_to_async

    owner = await sync_to_async(_owner)()
    if not owner:
        await update.message.reply_text("No owner account found.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /weigh <kg>  e.g. /weigh 118.5")
        return

    try:
        kg = Decimal(context.args[0])
    except InvalidOperation:
        await update.message.reply_text(f"Could not parse '{context.args[0]}' as a number.")
        return

    if not (30 <= kg <= 600):
        await update.message.reply_text("Weight must be between 30 and 600 kg.")
        return

    today = timezone.localdate()
    entry, created = await WeightEntry.objects.aupdate_or_create(
        user=owner,
        date=today,
        defaults={"weight_kg": kg},
    )
    verb = "Logged" if created else "Updated"
    await update.message.reply_text(f"{verb}: {kg} kg on {today}.")


async def cmd_log(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/log <food name> <grams> — log a meal entry by food name substring match."""
    from asgiref.sync import sync_to_async

    owner = await sync_to_async(_owner)()
    if not owner:
        await update.message.reply_text("No owner account found.")
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Usage: /log <food> <grams>  e.g. /log chicken 200")
        return

    try:
        grams = Decimal(context.args[-1])
    except InvalidOperation:
        await update.message.reply_text(
            f"Last argument must be grams (a number). Got: '{context.args[-1]}'"
        )
        return

    query = " ".join(context.args[:-1])
    food = await FoodItem.objects.filter(name__icontains=query).afirst()
    if not food:
        await update.message.reply_text(f"No food found matching '{query}'.")
        return

    await MealEntry.objects.acreate(user=owner, food=food, grams=grams)
    kcal = (grams / 100) * food.kcal_per_100g
    protein = (grams / 100) * food.protein_g
    await update.message.reply_text(
        f"Logged: {food.name} {grams}g — {kcal:.0f} kcal, {protein:.1f}g protein."
    )


async def habit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle a habit boolean from the evening inline keyboard."""
    from asgiref.sync import sync_to_async

    query = update.callback_query
    await query.answer()

    if not query.data or not query.data.startswith("habit:"):
        return

    field = query.data.removeprefix("habit:")
    valid_fields = {f for f, _ in protocol.HABIT_LABELS}
    if field not in valid_fields:
        return

    owner = await sync_to_async(_owner)()
    if not owner:
        return

    today = timezone.localdate()
    log, _ = await DailyLog.objects.aget_or_create(user=owner, date=today)
    setattr(log, field, not getattr(log, field))
    await log.asave(update_fields=[field, "updated_at"])

    # Rebuild the inline keyboard reflecting new state
    buttons = []
    for habit_field, label in protocol.HABIT_LABELS:
        done = bool(getattr(log, habit_field))
        tick = "✓ " if done else "☐ "
        buttons.append(
            [InlineKeyboardButton(text=f"{tick}{label}", callback_data=f"habit:{habit_field}")]
        )

    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(buttons))


class Command(BaseCommand):
    """Run the Telegram bot polling loop."""

    help = "Start the Telegram bot (long-polling)."

    def handle(self, *args, **options) -> None:
        token = settings.TELEGRAM_BOT_TOKEN
        if not token:
            self.stderr.write("TELEGRAM_BOT_TOKEN is not set. Exiting.")
            return

        app = Application.builder().token(token).build()
        app.add_handler(CommandHandler("start", cmd_start))
        app.add_handler(CommandHandler("today", cmd_today))
        app.add_handler(CommandHandler("weigh", cmd_weigh))
        app.add_handler(CommandHandler("log", cmd_log))
        app.add_handler(CallbackQueryHandler(habit_callback, pattern=r"^habit:"))

        self.stdout.write("Bot started (polling).")
        app.run_polling(allowed_updates=Update.ALL_TYPES)
