from rest_framework import serializers
from .models import CommitmentOccurrence
from .recurrence_engine import FREQUENCIES
from rest_framework.exceptions import ValidationError
from django.db.models import Q


class CalendarFilters(serializers.Serializer):
    q = serializers.CharField(max_length=200, required=False, allow_blank=True)
    status = serializers.ChoiceField(
        choices=[
            "pending",
            "in_progress",
            "awaiting_validation",
            "completed",
            "rejected",
            "cancelled",
        ],
        required=False,
        allow_blank=True,
    )
    priority = serializers.ChoiceField(
        choices=CommitmentOccurrence._meta.get_field("priority").choices,
        required=False,
        allow_blank=True,
    )
    periodicity = serializers.ChoiceField(choices=FREQUENCIES, required=False, allow_blank=True)
    unit = serializers.UUIDField(required=False, allow_null=True)
    entity = serializers.UUIDField(required=False, allow_null=True)
    category = serializers.UUIDField(required=False, allow_null=True)
    requester = serializers.UUIDField(required=False, allow_null=True)
    assignee = serializers.UUIDField(required=False, allow_null=True)
    date_start = serializers.DateField(required=False)
    date_end = serializers.DateField(required=False)

    def validate(self, data):
        start, end = data.get("date_start"), data.get("date_end")
        if start and end and (end < start or (end - start).days > 365):
            raise serializers.ValidationError("Período inválido: limite de 366 dias, inclusive.")
        return data


def parse_filters(params, required_period=False):
    keys = CalendarFilters().fields
    data = {key: params[key] for key in keys if key in params and params[key] not in ["", None]}
    serializer = CalendarFilters(data=data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    if required_period and not (data.get("date_start") and data.get("date_end")):
        raise ValidationError("Informe date_start e date_end.")
    return data


def filter_occurrences(qs, filters, deduplicate=True):
    if filters.get("q"):
        q = filters["q"]
        qs = qs.filter(
            Q(identifier__icontains=q) | Q(title__icontains=q) | Q(description__icontains=q)
        )
    for field in ["unit", "entity", "category", "requester"]:
        if filters.get(field):
            qs = qs.filter(**{f"definition__{field}_id": filters[field]})
    if filters.get("assignee"):
        qs = qs.filter(assignments__user_id=filters["assignee"])
    for field in ["status", "priority", "periodicity"]:
        if filters.get(field):
            qs = qs.filter(**{field: filters[field]})
    if filters.get("date_start"):
        qs = qs.filter(due_date__gte=filters["date_start"])
    if filters.get("date_end"):
        qs = qs.filter(due_date__lte=filters["date_end"])
    return qs.distinct() if deduplicate else qs
