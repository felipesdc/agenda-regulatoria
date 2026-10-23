from datetime import date
from rest_framework import serializers
from .recurrence_engine import FREQUENCIES, CALENDAR_CHOICES
from .serializers import StrictSerializer
from .models import Holiday, RecurrenceVersion, CommitmentOccurrence


class RuleSerializer(StrictSerializer):
    frequency = serializers.ChoiceField(choices=FREQUENCIES)
    calendar = serializers.ChoiceField(choices=CALENDAR_CHOICES, default="institution")
    start = serializers.DateField()
    end = serializers.DateField()
    count = serializers.IntegerField(min_value=1, max_value=1000, default=1000)
    month_mode = serializers.ChoiceField(
        choices=[
            "day",
            "first_day",
            "last_day",
            "business_day",
            "last_business_day",
            "weekday",
            "last_weekday",
        ],
        default="day",
    )
    month_day = serializers.IntegerField(min_value=1, max_value=31, required=False)
    ordinal = serializers.IntegerField(min_value=1, max_value=31, default=1)
    weekday = serializers.IntegerField(min_value=0, max_value=6, default=0)
    interval = serializers.IntegerField(min_value=1, max_value=365, default=1)
    interval_unit = serializers.ChoiceField(choices=["days", "business_days"], default="days")
    adjustment = serializers.ChoiceField(choices=["none", "next", "previous"], default="none")
    exceptions = serializers.ListField(child=serializers.DateField(), max_length=366, default=list)

    def validate(self, data):
        if data["end"] < data["start"] or (data["end"] - data["start"]).days > 3652:
            raise serializers.ValidationError(
                "Informe intervalo de até dez anos, com fim após início."
            )
        if not date(1900, 1, 1) <= data["start"] <= data["end"] <= date(2200, 12, 31):
            raise serializers.ValidationError("Datas permitidas: 1900 a 2200.")
        if data["month_mode"] == "weekday" and data["ordinal"] > 5:
            raise serializers.ValidationError("Ordinal semanal deve ser de 1 a 5.")
        if any(d < data["start"] or d > data["end"] for d in data["exceptions"]):
            raise serializers.ValidationError("Exceções devem pertencer ao período da regra.")
        return {
            k: v.isoformat()
            if isinstance(v, date)
            else [d.isoformat() for d in v]
            if k == "exceptions"
            else v
            for k, v in data.items()
        }


class PreviewInput(StrictSerializer):
    rule = RuleSerializer()
    through = serializers.DateField()


class PreviewOutput(serializers.Serializer):
    dates = serializers.ListField(child=serializers.DictField(child=serializers.DateField()))


class HolidaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Holiday
        fields = ["id", "date", "name", "kind", "active"]
        read_only_fields = ["id"]


class RecurrenceOutput(serializers.ModelSerializer):
    class Meta:
        model = RecurrenceVersion
        fields = [
            "id",
            "revision",
            "effective_from",
            "rule",
            "holidays",
            "template",
            "reason",
            "created_at",
        ]


class SeriesInput(StrictSerializer):
    revision = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=4000)
    scope = serializers.ChoiceField(choices=["future", "pending"])
    title = serializers.CharField(max_length=200, required=False)
    description = serializers.CharField(max_length=20000, required=False)
    legal_basis = serializers.CharField(max_length=10000, allow_blank=True, required=False)
    priority = serializers.ChoiceField(
        choices=CommitmentOccurrence._meta.get_field("priority").choices, required=False
    )
    rule = RuleSerializer(required=False)


class GenerateInput(StrictSerializer):
    through = serializers.DateField()


class GenerateOutput(serializers.Serializer):
    created = serializers.IntegerField()
