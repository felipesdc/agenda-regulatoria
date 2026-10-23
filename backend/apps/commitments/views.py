from django.db import transaction, IntegrityError
from django.db.models import Q, Exists, OuterRef
from django.utils import timezone
from rest_framework import viewsets, mixins, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError, PermissionDenied
from drf_spectacular.utils import extend_schema, OpenApiParameter
from apps.accounts.models import User, Membership
from apps.accounts.permissions import IsAdministrator, has_role
from apps.audit.services import record
from .models import (
    RegulatoryEntity,
    CommitmentCategory,
    CommitmentDefinition,
    CommitmentOccurrence,
    CommitmentAssignment,
)
from .serializers import (
    CatalogSerializer,
    CatalogEdit,
    CategorySerializer,
    PersonSerializer,
    CreateSerializer,
    EditSerializer,
    TransitionSerializer,
    ActionInput,
    ActionSerializer,
    OccurrenceSerializer,
    OccurrenceDetail,
    DefinitionSerializer,
)
from . import services


def scoped_occurrences(user):
    qs = CommitmentOccurrence.objects.filter(definition__unit__active=True)
    if not user.is_superuser:
        units = Membership.objects.filter(
            user=user, role="requester", unit__active=True
        ).values_list("unit_id", flat=True)
        executor_units = Membership.objects.filter(
            user=user, role="executor", unit__active=True
        ).values_list("unit_id", flat=True)
        qs = qs.alias(
            scope_assigned=Exists(
                CommitmentAssignment.objects.filter(occurrence_id=OuterRef("pk"), user=user)
            )
        ).filter(
            Q(definition__unit_id__in=units)
            | Q(scope_assigned=True, definition__unit_id__in=executor_units)
        )
    return qs.select_related(
        "definition__unit", "definition__requester", "definition__entity", "definition__category"
    ).prefetch_related("assignments__user", "definition__recurrence_versions")


class CatalogView(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    serializer_class = CatalogSerializer
    queryset = RegulatoryEntity.objects.all()

    def get_permissions(self):
        return (
            [IsAdministrator()]
            if self.action in ["create", "partial_update"]
            else super().get_permissions()
        )

    @extend_schema(request=CatalogEdit, responses=CatalogSerializer)
    @transaction.atomic
    def partial_update(self, request, pk=None):
        obj = self.get_queryset().select_for_update().get(pk=self.get_object().pk)
        serializer = CatalogEdit(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        before = {"name": obj.name, "active": obj.active}
        if before != {"name": data["expected_name"], "active": data["expected_active"]}:
            raise ValidationError("Cadastro alterado. Atualize antes de salvar.")
        obj.name, obj.active = data["name"], data["active"]
        try:
            with transaction.atomic():
                obj.save()
        except IntegrityError:
            raise ValidationError({"name": "Nome já utilizado."})
        record(
            request.user,
            "catalog.updated",
            obj,
            before=before,
            after={"name": obj.name, "active": obj.active},
            reason=data["reason"],
        )
        return Response(self.get_serializer(obj).data)

    @transaction.atomic
    def perform_create(self, serializer):
        obj = serializer.save()
        record(
            self.request.user,
            "catalog.created",
            obj,
            after={"name": obj.name, "active": obj.active},
        )


class CategoryView(CatalogView):
    serializer_class = CategorySerializer
    queryset = CommitmentCategory.objects.all()


class AssignableUsers(generics.ListAPIView):
    serializer_class = PersonSerializer

    @extend_schema(parameters=[OpenApiParameter("unit", str, required=True)])
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)

    def get_queryset(self):
        unit = self.request.query_params.get("unit", "")
        import uuid

        try:
            uuid.UUID(unit)
        except ValueError:
            raise ValidationError({"unit": "UUID de unidade obrigatório."})
        if not has_role(self.request.user, unit, "requester"):
            raise PermissionDenied("Sem permissão para atribuir nesta unidade.")
        return (
            User.objects.filter(
                is_active=True,
                memberships__unit_id=unit,
                memberships__role="executor",
                memberships__unit__active=True,
            )
            .distinct()
            .order_by("username")
        )


class DefinitionView(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = DefinitionSerializer
    lookup_value_regex = (
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    )

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return CommitmentDefinition.objects.none()
        return (
            CommitmentDefinition.objects.filter(
                occurrences__in=scoped_occurrences(self.request.user)
            )
            .distinct()
            .order_by("-created_at", "id")
        )

    @extend_schema(request=CreateSerializer, responses={201: OccurrenceDetail})
    def create(self, request, *args, **kwargs):
        serializer = CreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        occurrence = services.create_commitment(request.user, serializer.validated_data)
        return Response(OccurrenceDetail(occurrence, context={"request": request}).data, status=201)


class OccurrenceView(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = OccurrenceSerializer
    lookup_value_regex = DefinitionView.lookup_value_regex

    def get_serializer_class(self):
        return OccurrenceDetail if self.action == "retrieve" else OccurrenceSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return CommitmentOccurrence.objects.none()
        qs = scoped_occurrences(self.request.user)
        params = self.request.query_params
        if params.get("mine") == "true":
            qs = qs.filter(assignments__user=self.request.user)
        if params.get("validation") == "true":
            qs = qs.filter(status="awaiting_validation", definition__requester=self.request.user)
        if params.get("overdue") == "true":
            qs = qs.filter(due_date__lt=timezone.localdate()).exclude(
                status__in=["completed", "cancelled"]
            )
        from .calendar_filters import parse_filters, filter_occurrences

        qs = filter_occurrences(qs, parse_filters(params))
        if self.action == "retrieve":
            qs = qs.select_related("form_version").prefetch_related(
                "actions__author", "transitions__actor", "versions"
            )
        return qs.distinct()

    @extend_schema(request=EditSerializer, responses=OccurrenceDetail)
    @action(detail=True, methods=["patch"], url_path="edit")
    def edit(self, request, pk=None):
        occurrence = self.get_object()
        serializer = EditSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Status and identifiers cannot be supplied through arbitrary PATCH.
        unknown = set(request.data) - set(serializer.fields)
        if unknown:
            raise ValidationError({"detail": "Campos não editáveis: " + ", ".join(sorted(unknown))})
        updated = services.update_occurrence(request.user, occurrence, serializer.validated_data)
        return Response(OccurrenceDetail(updated, context={"request": request}).data)

    @extend_schema(request=ActionInput, responses={201: ActionSerializer})
    @action(detail=True, methods=["post"], url_path="actions")
    def add_action(self, request, pk=None):
        occurrence = self.get_object()
        serializer = ActionInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = services.add_action(request.user, occurrence, serializer.validated_data["text"])
        return Response(ActionSerializer(action).data, status=201)

    @extend_schema(request=TransitionSerializer, responses=OccurrenceDetail)
    @action(detail=True, methods=["post"], url_path="transition")
    def transition(self, request, pk=None):
        occurrence = self.get_object()
        serializer = TransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = services.transition(
            request.user,
            occurrence,
            serializer.validated_data["operation"],
            serializer.validated_data["reason"],
            serializer.validated_data["revision"],
        )
        return Response(OccurrenceDetail(updated, context={"request": request}).data)
