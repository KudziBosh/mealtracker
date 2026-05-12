"""Admin registration — the initial UI for slice 1."""

from django.contrib import admin

from .models import DailyLog, WeightEntry


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


@admin.register(WeightEntry)
class WeightEntryAdmin(admin.ModelAdmin):
    list_display = ("date", "user", "weight_kg")
    list_filter = ("user",)
    date_hierarchy = "date"
    ordering = ("-date",)
