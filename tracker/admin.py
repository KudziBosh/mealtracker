"""Admin registration — the initial UI for slice 1."""

from django.contrib import admin

from .models import (
    DailyLog,
    FoodItem,
    MealEntry,
    MealTemplate,
    MealTemplateItem,
    TelegramSettings,
    WeightEntry,
)


@admin.register(FoodItem)
class FoodItemAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "kcal_per_100g",
        "protein_g",
        "fat_g",
        "carb_g",
        "satiety_index",
        "common_unit",
        "default_grams",
    )
    list_filter = ("satiety_index",)
    list_editable = ("default_grams",)
    search_fields = ("name", "common_unit", "notes")
    ordering = ("name",)


class MealTemplateItemInline(admin.TabularInline):
    """Edit the ingredient lines of a recipe inline with the recipe itself."""

    model = MealTemplateItem
    extra = 1
    autocomplete_fields = ("food",)


@admin.register(MealTemplate)
class MealTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "item_count")
    list_filter = ("category",)
    search_fields = ("name", "notes")
    ordering = ("category", "name")
    inlines = [MealTemplateItemInline]

    @admin.display(description="Ingredients")
    def item_count(self, obj: MealTemplate) -> int:
        return obj.items.count()


@admin.register(DailyLog)
class DailyLogAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "user",
        "walked_minutes",
        "hit_protein",
        "under_calories",
        "walked_30",
        "ate_breakfast",
        "no_alcohol_or_sugar",
        "habits_completed",
    )
    list_filter = ("date", "user", "hit_protein", "walked_30")
    search_fields = ("notes",)
    date_hierarchy = "date"
    ordering = ("-date",)


@admin.register(MealEntry)
class MealEntryAdmin(admin.ModelAdmin):
    list_display = ("eaten_at", "user", "food", "grams", "kcal", "protein_g")
    list_filter = ("eaten_at", "user", "food")
    search_fields = ("food__name",)
    date_hierarchy = "eaten_at"
    ordering = ("-eaten_at",)


@admin.register(WeightEntry)
class WeightEntryAdmin(admin.ModelAdmin):
    list_display = ("date", "user", "weight_kg")
    list_filter = ("user",)
    date_hierarchy = "date"
    ordering = ("-date",)


@admin.register(TelegramSettings)
class TelegramSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "chat_id",
        "morning_ping_time",
        "evening_ping_time",
        "weekly_summary_day",
        "weekly_summary_time",
    )
    readonly_fields = ("id",)

    def has_add_permission(self, request: object) -> bool:
        return not TelegramSettings.objects.exists()
