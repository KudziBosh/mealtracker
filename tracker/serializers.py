"""DRF serializers for the minimal tracker API."""

from __future__ import annotations

from django.utils import timezone
from rest_framework import serializers

from tracker import protocol
from tracker.models import DailyLog, FoodItem, MealEntry, WeightEntry


class FoodItemSerializer(serializers.ModelSerializer):
    """Serialize a food item and its per-100g macro values."""

    class Meta:
        model = FoodItem
        fields = [
            "id",
            "name",
            "kcal_per_100g",
            "protein_g",
            "fat_g",
            "carb_g",
            "satiety_index",
            "common_unit",
            "notes",
        ]


class MealEntrySerializer(serializers.ModelSerializer):
    """Serialize meal entries, including computed macros for the logged grams."""

    food = FoodItemSerializer(read_only=True)
    food_id = serializers.PrimaryKeyRelatedField(
        queryset=FoodItem.objects.all(),
        source="food",
        write_only=True,
    )
    kcal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    protein_g = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    fat_g = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    carb_g = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = MealEntry
        fields = [
            "id",
            "eaten_at",
            "food",
            "food_id",
            "grams",
            "kcal",
            "protein_g",
            "fat_g",
            "carb_g",
        ]

    def create(self, validated_data: dict) -> MealEntry:
        """Create a meal for the authenticated owner."""
        return MealEntry.objects.create(user=self.context["request"].user, **validated_data)


class DailyLogSerializer(serializers.ModelSerializer):
    """Serialize a daily log with habit completion counts."""

    habits_completed = serializers.IntegerField(read_only=True)
    habits_total = serializers.IntegerField(read_only=True)

    class Meta:
        model = DailyLog
        fields = [
            "id",
            "date",
            "walked_minutes",
            "steps",
            "hit_protein",
            "under_calories",
            "walked_30",
            "ate_breakfast",
            "no_alcohol_or_sugar",
            "notes",
            "habits_completed",
            "habits_total",
        ]


class DailyLogUpdateSerializer(serializers.Serializer):
    """Validate the narrow set of fields the API may update on a daily log."""

    toggle = serializers.ChoiceField(
        choices=[field for field, _label in protocol.HABIT_LABELS],
        required=False,
        write_only=True,
    )
    walked_minutes = serializers.IntegerField(min_value=0, required=False)
    steps = serializers.IntegerField(min_value=0, allow_null=True, required=False)
    hit_protein = serializers.BooleanField(required=False)
    under_calories = serializers.BooleanField(required=False)
    walked_30 = serializers.BooleanField(required=False)
    ate_breakfast = serializers.BooleanField(required=False)
    no_alcohol_or_sugar = serializers.BooleanField(required=False)

    def validate(self, attrs: dict) -> dict:
        """Require at least one allowed update."""
        if not attrs:
            raise serializers.ValidationError("Provide at least one field to update.")
        return attrs


class WeightEntrySerializer(serializers.ModelSerializer):
    """Serialize a weigh-in for the authenticated owner."""

    date = serializers.DateField(required=False, default=timezone.localdate)

    class Meta:
        model = WeightEntry
        fields = ["id", "date", "weight_kg", "notes"]

    def create(self, validated_data: dict) -> WeightEntry:
        """Create a weight entry for the authenticated owner."""
        return WeightEntry.objects.create(user=self.context["request"].user, **validated_data)
