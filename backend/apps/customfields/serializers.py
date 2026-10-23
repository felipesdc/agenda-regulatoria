from rest_framework import serializers
from apps.commitments.serializers import StrictSerializer
from apps.commitments.models import CommitmentCategory
from .models import CustomFieldDefinition, FormVersion
from .validation import KINDS, validate_metadata


class FieldInput(StrictSerializer):
    key = serializers.CharField(max_length=50)
    name = serializers.CharField(max_length=160)
    kind = serializers.ChoiceField(choices=list(KINDS.items()))
    description = serializers.CharField(max_length=4000, allow_blank=True, default="")
    required = serializers.BooleanField(default=False)
    default = serializers.JSONField(default=None, allow_null=True)
    rules = serializers.JSONField(default=dict)
    options = serializers.JSONField(default=list)
    order = serializers.IntegerField(min_value=0, max_value=1000, default=0)
    active = serializers.BooleanField(default=True)
    revision = serializers.IntegerField(min_value=0)
    reason = serializers.CharField(max_length=4000)

    def validate(self, data):
        return validate_metadata(data)


class FieldOutput(serializers.ModelSerializer):
    class Meta:
        model = CustomFieldDefinition
        fields = [
            "id",
            "key",
            "name",
            "kind",
            "description",
            "required",
            "default",
            "rules",
            "options",
            "order",
            "active",
            "revision",
        ]


class FormInput(StrictSerializer):
    category = serializers.PrimaryKeyRelatedField(
        queryset=CommitmentCategory.objects.filter(active=True)
    )
    name = serializers.CharField(max_length=160)
    fields = serializers.ListField(child=serializers.UUIDField(), max_length=50, allow_empty=True)
    revision = serializers.IntegerField(min_value=0)
    reason = serializers.CharField(max_length=4000)

    def validate_fields(self, values):
        if len(values) != len(set(values)):
            raise serializers.ValidationError("Campos duplicados.")
        return values


class FormOutput(serializers.ModelSerializer):
    category = serializers.UUIDField(source="category_id", read_only=True)

    class Meta:
        model = FormVersion
        fields = ["id", "category", "name", "revision", "fields", "reason", "created_at"]
