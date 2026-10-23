from rest_framework import serializers
from apps.commitments.models import CommitmentCategory, CommitmentDefinition
from apps.commitments.serializers import StrictSerializer
from .models import NotificationDelivery, NotificationAttempt, NotificationPolicy
from .services import event_label


class AttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationAttempt
        fields = ["number", "recipient_email", "stage", "error_code", "reason", "created_at"]


class DeliverySerializer(serializers.ModelSerializer):
    kind = serializers.CharField(source="event.kind", read_only=True)
    kind_label = serializers.SerializerMethodField()
    identifier = serializers.CharField(source="event.snapshot.identifier", read_only=True)
    title = serializers.CharField(source="event.snapshot.title", read_only=True)
    occurrence = serializers.UUIDField(source="event.occurrence_id", read_only=True)
    event_id = serializers.UUIDField(read_only=True)
    recipient_name = serializers.CharField(source="recipient.username", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    history = AttemptSerializer(many=True, read_only=True)
    message_id = serializers.CharField(read_only=True)

    def get_kind_label(self, obj) -> str:
        return event_label(obj.event)

    class Meta:
        model = NotificationDelivery
        fields = [
            "id",
            "event_id",
            "kind",
            "kind_label",
            "identifier",
            "title",
            "occurrence",
            "recipient_name",
            "recipient_email",
            "status",
            "status_label",
            "attempts",
            "retry_limit",
            "next_attempt_at",
            "accepted_at",
            "last_error",
            "message_id",
            "created_at",
            "history",
        ]


class RequeueInput(StrictSerializer):
    reason = serializers.CharField(max_length=4000)
    acknowledge_duplicate_risk = serializers.BooleanField(default=False)


class EmailInput(StrictSerializer):
    email = serializers.EmailField(max_length=254)


class EmailOutput(serializers.Serializer):
    email = serializers.EmailField(allow_blank=True)


class PolicyInput(StrictSerializer):
    category = serializers.PrimaryKeyRelatedField(
        queryset=CommitmentCategory.objects.filter(active=True), required=False, allow_null=True
    )
    definition = serializers.PrimaryKeyRelatedField(
        queryset=CommitmentDefinition.objects.filter(unit__active=True),
        required=False,
        allow_null=True,
    )
    enabled = serializers.BooleanField(default=True)
    offsets = serializers.JSONField()
    basis = serializers.ChoiceField(choices=["calendar", "business"], default="calendar")
    calendar = serializers.ChoiceField(
        choices=NotificationPolicy._meta.get_field("calendar").choices, default="institution"
    )
    revision = serializers.IntegerField(min_value=0, default=0)
    reason = serializers.CharField(max_length=4000)

    def validate_offsets(self, value):
        if (
            not isinstance(value, list)
            or not 1 <= len(value) <= 16
            or any(type(n) is not int or not -365 <= n <= 365 for n in value)
            or len(set(value)) != len(value)
        ):
            raise serializers.ValidationError(
                "Informe 1 a 16 intervalos inteiros únicos entre -365 e 365."
            )
        return sorted(value, reverse=True)

    def validate(self, data):
        if bool(data.get("category")) == bool(data.get("definition")):
            raise serializers.ValidationError("Informe exatamente uma categoria ou definição.")
        return data


class PolicyOutput(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True, default="")
    definition_identifier = serializers.CharField(
        source="definition.identifier", read_only=True, default=""
    )

    class Meta:
        model = NotificationPolicy
        fields = [
            "id",
            "category",
            "definition",
            "category_name",
            "definition_identifier",
            "enabled",
            "offsets",
            "basis",
            "calendar",
            "revision",
            "updated_at",
        ]


class JobOutput(serializers.Serializer):
    name = serializers.CharField()
    last_success_at = serializers.DateTimeField(allow_null=True)
    processed = serializers.IntegerField()


class MonitorOutput(serializers.Serializer):
    counts = serializers.DictField(child=serializers.IntegerField())
    oldest_pending_at = serializers.DateTimeField(allow_null=True)
    jobs = JobOutput(many=True)


class QueuedOutput(serializers.Serializer):
    queued = serializers.BooleanField()
