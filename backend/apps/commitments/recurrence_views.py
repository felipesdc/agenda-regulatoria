from django.db import transaction
from rest_framework import generics, mixins, viewsets
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from drf_spectacular.utils import extend_schema
from apps.accounts.permissions import IsAdministrator
from apps.audit.services import record
from .models import Holiday
from .views import OccurrenceView
from .services import can_manage
from .recurrence_serializers import (
    HolidaySerializer,
    PreviewInput,
    PreviewOutput,
    SeriesInput,
    RecurrenceOutput,
    GenerateInput,
    GenerateOutput,
)
from .recurrence_services import holiday_snapshot, change_series, generate, validated_dates


class HolidayView(
    mixins.ListModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet
):
    queryset = Holiday.objects.all()
    serializer_class = HolidaySerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_permissions(self):
        return (
            [IsAdministrator()]
            if self.action in ["create", "partial_update"]
            else super().get_permissions()
        )

    @transaction.atomic
    def perform_create(self, serializer):
        obj = serializer.save()
        record(self.request.user, "holiday.created", obj, after=HolidaySerializer(obj).data)

    @transaction.atomic
    def perform_update(self, serializer):
        before = HolidaySerializer(serializer.instance).data
        obj = serializer.save()
        record(
            self.request.user,
            "holiday.updated",
            obj,
            before=before,
            after=HolidaySerializer(obj).data,
        )


class PreviewView(generics.GenericAPIView):
    serializer_class = PreviewInput

    @extend_schema(request=PreviewInput, responses=PreviewOutput)
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        dates = [
            {"scheduled_date": nominal, "due_date": due}
            for nominal, due in validated_dates(
                data["rule"], data["through"], holiday_snapshot(data["rule"])
            )
        ]
        return Response({"dates": dates})


class SeriesOccurrenceView(OccurrenceView):
    @extend_schema(request=SeriesInput, responses=RecurrenceOutput)
    @action(detail=True, methods=["post"], url_path="series")
    def series(self, request, pk=None):
        occurrence = self.get_object()
        serializer = SeriesInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            RecurrenceOutput(
                change_series(request.user, occurrence, serializer.validated_data)
            ).data
        )

    @extend_schema(request=GenerateInput, responses=GenerateOutput)
    @action(detail=True, methods=["post"], url_path="generate")
    def generate(self, request, pk=None):
        occurrence = self.get_object()
        if not can_manage(request.user, occurrence):
            raise PermissionDenied("Sem permissão para gerar esta série.")
        if not occurrence.recurrence_version_id:
            raise ValidationError("Ocorrência única não possui série.")
        serializer = GenerateInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            {
                "created": generate(
                    occurrence.definition, serializer.validated_data["through"], request.user
                )
            }
        )
