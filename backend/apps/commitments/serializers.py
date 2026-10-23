from rest_framework import serializers
from apps.accounts.models import User, Membership
from apps.organizations.models import OrganizationalUnit
from .models import (
    RegulatoryEntity,
    CommitmentCategory,
    CommitmentDefinition,
    CommitmentOccurrence,
    ActionRecord,
    WorkflowTransition,
    OccurrenceVersion,
)
from .services import available_transitions


class CatalogSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegulatoryEntity
        fields = ["id", "name", "active"]
        read_only_fields = ["id"]


class CategorySerializer(CatalogSerializer):
    class Meta(CatalogSerializer.Meta):
        model = CommitmentCategory


class PersonSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    def get_name(self, obj) -> str:
        return obj.get_full_name() or obj.username

    class Meta:
        model = User
        fields = ["id", "username", "name"]


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError(
                    {"detail": "Campos não permitidos: " + ", ".join(sorted(unknown))}
                )
        return super().to_internal_value(data)


class CatalogEdit(StrictSerializer):
    name = serializers.CharField(max_length=160)
    active = serializers.BooleanField()
    expected_name = serializers.CharField(max_length=160)
    expected_active = serializers.BooleanField()
    reason = serializers.CharField(max_length=4000)


class RecurrenceInput(serializers.JSONField):
    def to_internal_value(self, data):
        from .recurrence_serializers import RuleSerializer

        serializer = RuleSerializer(data=super().to_internal_value(data))
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data


class CreateSerializer(StrictSerializer):
    form_version = serializers.UUIDField(required=False, allow_null=True)
    custom_values = serializers.JSONField(required=False, default=dict)
    recurrence = RecurrenceInput(required=False)
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(max_length=20000)
    legal_basis = serializers.CharField(max_length=10000, allow_blank=True, default="")
    entity = serializers.PrimaryKeyRelatedField(
        queryset=RegulatoryEntity.objects.filter(active=True)
    )
    category = serializers.PrimaryKeyRelatedField(
        queryset=CommitmentCategory.objects.filter(active=True)
    )
    unit = serializers.PrimaryKeyRelatedField(
        queryset=OrganizationalUnit.objects.filter(active=True)
    )
    assignees = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(is_active=True), many=True
    )
    reference_date = serializers.DateField()
    due_date = serializers.DateField()
    priority = serializers.ChoiceField(
        choices=CommitmentOccurrence._meta.get_field("priority").choices, default="normal"
    )


class EditSerializer(StrictSerializer):
    custom_values = serializers.JSONField(required=False)
    title = serializers.CharField(max_length=200, required=False)
    description = serializers.CharField(max_length=20000, required=False)
    legal_basis = serializers.CharField(max_length=10000, allow_blank=True, required=False)
    reference_date = serializers.DateField(required=False)
    due_date = serializers.DateField(required=False)
    priority = serializers.ChoiceField(
        choices=CommitmentOccurrence._meta.get_field("priority").choices, required=False
    )
    assignees = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(is_active=True), many=True, required=False
    )
    reason = serializers.CharField(max_length=4000)
    revision = serializers.IntegerField(min_value=1)


class TransitionSerializer(StrictSerializer):
    operation = serializers.ChoiceField(
        choices=["start", "submit", "approve", "reject", "cancel", "reopen"]
    )
    reason = serializers.CharField(max_length=4000, allow_blank=True, default="")
    revision = serializers.IntegerField(min_value=1)


class ActionInput(StrictSerializer):
    text = serializers.CharField(max_length=20000)


class ActionSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.username", read_only=True)

    class Meta:
        model = ActionRecord
        fields = ["id", "author_name", "text", "created_at"]


class TransitionOutput(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.username", read_only=True)

    class Meta:
        model = WorkflowTransition
        fields = ["id", "actor_name", "previous_status", "new_status", "reason", "created_at"]


class VersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = OccurrenceVersion
        fields = ["revision", "snapshot", "created_at"]


class DefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommitmentDefinition
        fields = [
            "id",
            "identifier",
            "title",
            "description",
            "legal_basis",
            "entity",
            "category",
            "unit",
            "requester",
            "created_at",
        ]


class OccurrenceSerializer(serializers.ModelSerializer):
    entity_name = serializers.CharField(source="definition.entity.name")
    category_name = serializers.CharField(source="definition.category.name")
    unit_name = serializers.CharField(source="definition.unit.name")
    unit = serializers.UUIDField(source="definition.unit_id", read_only=True)
    requester_name = serializers.CharField(source="definition.requester.username")
    assignees = serializers.SerializerMethodField()
    overdue = serializers.BooleanField(read_only=True)
    available_transitions = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    can_add_action = serializers.SerializerMethodField()
    can_manage_series = serializers.SerializerMethodField()
    series_revision = serializers.SerializerMethodField()

    def get_can_manage_series(self, obj) -> bool:
        return self._access(obj)[0] and obj.recurrence_version_id is not None

    def get_series_revision(self, obj) -> int:
        versions = list(obj.definition.recurrence_versions.all())
        return versions[-1].revision if versions else 0

    def get_assignees(self, obj) -> list[dict]:
        return PersonSerializer([a.user for a in obj.assignments.all()], many=True).data

    def _access(self, obj):
        user = self.context["request"].user
        if "role_pairs" not in self.context:
            self.context["role_pairs"] = set(
                Membership.objects.filter(user=user, unit__active=True).values_list(
                    "unit_id", "role"
                )
            )
        roles = self.context["role_pairs"]
        assigned = any(a.user_id == user.pk for a in obj.assignments.all())
        unit = obj.definition.unit
        active = user.is_active and unit.active
        manage = (
            active
            and (user.is_superuser or (unit.pk, "requester") in roles)
            and (user.is_superuser or obj.definition.requester_id == user.pk)
        )
        execute = active and assigned and (user.is_superuser or (unit.pk, "executor") in roles)
        return manage, execute, assigned

    def get_available_transitions(self, obj) -> list[str]:
        return available_transitions(self.context["request"].user, obj, self._access(obj))

    def get_can_edit(self, obj) -> bool:
        return self._access(obj)[0] and obj.status in [
            "pending",
            "in_progress",
            "rejected",
        ]

    def get_can_add_action(self, obj) -> bool:
        return self._access(obj)[1] and obj.status in [
            "in_progress",
            "rejected",
        ]

    class Meta:
        model = CommitmentOccurrence
        fields = [
            "id",
            "identifier",
            "scheduled_date",
            "periodicity",
            "recurrence_version",
            "series_revision",
            "can_manage_series",
            "definition",
            "title",
            "description",
            "legal_basis",
            "reference_date",
            "due_date",
            "priority",
            "status",
            "revision",
            "overdue",
            "entity_name",
            "category_name",
            "unit_name",
            "unit",
            "requester_name",
            "assignees",
            "available_transitions",
            "can_edit",
            "can_add_action",
            "completed_at",
            "created_at",
        ]


class OccurrenceDetail(OccurrenceSerializer):
    form_schema = serializers.SerializerMethodField()

    def get_form_schema(self, obj) -> dict | None:
        from apps.customfields.serializers import FormOutput

        return FormOutput(obj.form_version).data if obj.form_version_id else None

    actions = ActionSerializer(many=True, read_only=True)
    transitions = TransitionOutput(many=True, read_only=True)
    versions = VersionSerializer(many=True, read_only=True)
    series_versions = serializers.SerializerMethodField()

    def get_series_versions(self, obj) -> list[dict]:
        from .recurrence_serializers import RecurrenceOutput

        return RecurrenceOutput(obj.definition.recurrence_versions.all(), many=True).data

    class Meta(OccurrenceSerializer.Meta):
        fields = OccurrenceSerializer.Meta.fields + [
            "form_version",
            "custom_values",
            "form_schema",
            "actions",
            "transitions",
            "versions",
            "series_versions",
        ]
