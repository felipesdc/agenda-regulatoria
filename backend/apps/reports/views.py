import hashlib
import json
from datetime import timedelta
from django.db import transaction, connection
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Count, Q, F
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import generics, serializers, viewsets, mixins
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from drf_spectacular.utils import extend_schema, extend_schema_serializer, OpenApiParameter
from apps.commitments.calendar_filters import CalendarFilters, parse_filters
from apps.commitments.serializers import OccurrenceSerializer
from apps.audit.services import record
from .services import cohort, metrics, detailed, ACTIVE, counts
from .exports import rows, csv_bytes, xlsx_bytes
from .models import ReportFavorite


class ObjectOutput(serializers.Serializer):
    data = serializers.JSONField()


class DashboardOutput(serializers.Serializer):
    as_of = serializers.DateField()
    metrics = serializers.JSONField()
    completed_this_month = serializers.IntegerField()
    attention = OccurrenceSerializer(many=True)


class SummaryOutput(serializers.Serializer):
    as_of = serializers.DateField()
    metrics = serializers.JSONField()
    filters = serializers.JSONField()
    period_basis = serializers.CharField()
    definitions = serializers.DictField(child=serializers.CharField())


class PrivateResponse:
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store, private"
        return response


def report_filters(params):
    allowed = set(CalendarFilters().fields) | {"overdue", "group_by", "page", "output"}
    if set(params) - allowed:
        raise ValidationError("Parâmetro não reconhecido.")
    filters = parse_filters(params, required_period=True)
    if params.get("overdue", "false") not in ["true", "false"]:
        raise ValidationError({"overdue": "Use true ou false."})
    return filters


def report_cohort(user, params):
    filters = report_filters(params)
    qs = cohort(user, filters)
    if params.get("overdue") == "true":
        qs = qs.filter(status__in=ACTIVE, due_date__lt=timezone.localdate())
    return qs, filters


class Dashboard(PrivateResponse, generics.GenericAPIView):
    serializer_class = DashboardOutput

    @extend_schema(responses=DashboardOutput)
    def get(self, request):
        today = timezone.localdate()
        qs = cohort(request.user, {})
        start = today.replace(day=1)
        end = (start + timedelta(days=32)).replace(day=1)
        dashboard_counts = counts(qs)
        completed_this_month = qs.filter(
            status="completed", completed_at__date__gte=start, completed_at__date__lt=end
        ).count()
        attention = detailed(
            qs.filter(
                Q(status__in=ACTIVE, due_date__lte=today + timedelta(days=7))
                | Q(status="awaiting_validation")
            )
        )[:10]
        return Response(
            {
                "as_of": today,
                "metrics": dashboard_counts,
                "completed_this_month": completed_this_month,
                "attention": OccurrenceSerializer(
                    attention, many=True, context={"request": request}
                ).data,
            }
        )


class Summary(PrivateResponse, generics.GenericAPIView):
    serializer_class = SummaryOutput

    @extend_schema(
        parameters=[CalendarFilters, OpenApiParameter("overdue", bool)], responses=SummaryOutput
    )
    def get(self, request):
        qs, filters = report_cohort(request.user, request.query_params)
        return Response(
            {
                "as_of": timezone.localdate(),
                "filters": filters,
                "metrics": metrics(qs),
                "period_basis": "due_date",
                "definitions": {
                    "on_time": "Concluídas com data final conhecida cuja aprovação, no fuso institucional, ocorreu até o vencimento / concluídas com data final conhecida.",
                    "completion": "Horas entre criação da ocorrência e aprovação final; amostra de concluídas com timestamps válidos.",
                    "validation": "Horas entre a última submissão anterior à aprovação final e essa aprovação; amostra com ambas as datas.",
                    "groups": "Responsáveis: uma ocorrência é contada para cada atribuição atual; grupos não são somáveis entre usuários.",
                },
            }
        )


class ReportOccurrences(PrivateResponse, generics.ListAPIView):
    serializer_class = OccurrenceSerializer

    @extend_schema(parameters=[CalendarFilters, OpenApiParameter("overdue", bool)])
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            from apps.commitments.models import CommitmentOccurrence

            return CommitmentOccurrence.objects.none()
        qs, _ = report_cohort(self.request.user, self.request.query_params)
        return detailed(qs)


class GroupOutput(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    total = serializers.IntegerField()
    overdue = serializers.IntegerField()
    completed = serializers.IntegerField()


class Groups(PrivateResponse, generics.ListAPIView):
    serializer_class = GroupOutput

    @extend_schema(
        parameters=[
            CalendarFilters,
            OpenApiParameter("overdue", bool),
            OpenApiParameter("group_by", str, enum=["unit", "entity", "assignee", "periodicity"]),
        ]
    )
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)

    def get_queryset(self):
        qs, _ = report_cohort(self.request.user, self.request.query_params)
        group = self.request.query_params.get("group_by", "unit")
        mapping = {
            "unit": ("definition__unit_id", "definition__unit__name"),
            "entity": ("definition__entity_id", "definition__entity__name"),
            "assignee": ("assignments__user_id", "assignments__user__username"),
            "periodicity": ("periodicity", "periodicity"),
        }
        if group not in mapping:
            raise ValidationError({"group_by": "Agrupamento inválido."})
        key, name = mapping[group]
        # IDs normalized before this join; assignment filters do not restrict group labels.
        return (
            qs.order_by()
            .values(key, name)
            .annotate(
                total=Count("pk", distinct=True),
                overdue=Count(
                    "pk",
                    distinct=True,
                    filter=Q(status__in=ACTIVE, due_date__lt=timezone.localdate()),
                ),
                completed=Count("pk", distinct=True, filter=Q(status="completed")),
            )
            .order_by("-total", name)
            .annotate(group_id=F(key), group_name=F(name))
        )

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        page = self.paginate_queryset(qs)
        output = [
            {
                "id": r["group_id"],
                "name": r["group_name"],
                "total": r["total"],
                "overdue": r["overdue"],
                "completed": r["completed"],
            }
            for r in page
        ]
        return self.get_paginated_response(output)


class Export(PrivateResponse, generics.GenericAPIView):
    serializer_class = ObjectOutput

    @extend_schema(
        parameters=[
            CalendarFilters,
            OpenApiParameter("overdue", bool),
            OpenApiParameter("output", str, enum=["csv", "xlsx"]),
        ],
        responses={
            (200, "text/csv"): bytes,
            (200, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"): bytes,
        },
    )
    @transaction.atomic
    def get(self, request):
        if connection.vendor == "postgresql" and not connection.savepoint_ids:
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        qs, filters = report_cohort(request.user, request.query_params)
        output = request.query_params.get("output", "csv")
        if output not in ["csv", "xlsx"]:
            raise ValidationError({"output": "Use csv ou xlsx."})
        count = qs.count()
        if count > 5000:
            raise ValidationError("Exportação limitada a 5000 ocorrências; restrinja os filtros.")
        export_qs = (
            qs.select_related(
                "definition__unit",
                "definition__entity",
                "definition__category",
                "definition__requester",
            )
            .prefetch_related("assignments__user")
            .defer(
                "definition__custom_values", "definition__description", "definition__legal_basis"
            )
            .order_by("due_date", "identifier")
        )
        table = rows(export_qs.iterator(chunk_size=50))
        content = csv_bytes(table) if output == "csv" else xlsx_bytes(table)
        if len(content) > 20 * 1024 * 1024:
            raise ValidationError("Exportação excede 20 MiB; restrinja os filtros.")
        record(
            request.user,
            "report.exported",
            request.user,
            after={
                "output": output,
                "count": count,
                "filters": json.loads(json.dumps(filters, cls=DjangoJSONEncoder)),
                "overdue": request.query_params.get("overdue", "false"),
                "sha256": hashlib.sha256(content).hexdigest(),
            },
        )
        mime = (
            "text/csv; charset=utf-8"
            if output == "csv"
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response = HttpResponse(content, content_type=mime)
        response["Content-Disposition"] = f'attachment; filename="compromissos.{output}"'
        response["Cache-Control"] = "no-store, private"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class FavoriteOutput(serializers.ModelSerializer):
    class Meta:
        model = ReportFavorite
        fields = ["id", "name", "filters"]
        read_only_fields = ["id"]

    def validate_filters(self, value):
        if not isinstance(value, dict) or set(value) - (
            set(CalendarFilters().fields) | {"overdue"}
        ):
            raise ValidationError("Filtros de relatório inválidos.")
        value = dict(value)
        if type(value.get("overdue")) is bool:
            value["overdue"] = "true" if value["overdue"] else "false"
        normalized = report_filters(value)
        normalized["overdue"] = value.get("overdue", "false")
        return json.loads(json.dumps(normalized, cls=DjangoJSONEncoder))


class FavoriteView(
    PrivateResponse,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = FavoriteOutput

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ReportFavorite.objects.none()
        return ReportFavorite.objects.filter(owner=self.request.user)

    @transaction.atomic
    def perform_create(self, serializer):
        from django.db import IntegrityError

        try:
            with transaction.atomic():
                obj = serializer.save(owner=self.request.user)
        except IntegrityError:
            raise ValidationError({"name": "Já existe favorito com este nome."})
        record(
            self.request.user,
            "report_favorite.created",
            obj,
            after={"name": obj.name, "filters": obj.filters},
        )

    @transaction.atomic
    def perform_destroy(self, instance):
        record(
            self.request.user,
            "report_favorite.deleted",
            instance,
            before={"name": instance.name, "filters": instance.filters},
        )
        instance.delete()


@extend_schema_serializer(many=False)
class PendingCenterOutput(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = OccurrenceSerializer(many=True)
    as_of = serializers.DateField()
    counts = serializers.DictField(child=serializers.IntegerField())
    bucket = serializers.CharField()


class PendingCenter(PrivateResponse, generics.ListAPIView):
    serializer_class = OccurrenceSerializer

    @extend_schema(
        parameters=[OpenApiParameter("bucket", str, enum=["overdue", "upcoming", "validation"])],
        responses=PendingCenterOutput(many=False),
    )
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)

    def list(self, request, *args, **kwargs):
        if set(request.query_params) - {"bucket", "page"}:
            raise ValidationError("Parâmetro não reconhecido.")
        bucket = request.query_params.get("bucket", "overdue")
        today = timezone.localdate()
        filters = {
            "overdue": Q(status__in=ACTIVE, due_date__lt=today),
            "upcoming": Q(
                status__in=ACTIVE, due_date__gte=today, due_date__lte=today + timedelta(days=7)
            ),
            "validation": Q(status="awaiting_validation"),
        }
        if bucket not in filters:
            raise ValidationError({"bucket": "Selecione overdue, upcoming ou validation."})
        qs = cohort(request.user, {})
        totals = qs.aggregate(**{key: Count("pk", filter=value) for key, value in filters.items()})
        page = self.paginate_queryset(
            detailed(qs.filter(filters[bucket])).order_by("due_date", "identifier", "id")
        )
        response = self.get_paginated_response(self.get_serializer(page, many=True).data)
        # Keep the selected card consistent with pagination if a workflow changes concurrently.
        totals[bucket] = response.data["count"]
        response.data.update({"as_of": today, "counts": totals, "bucket": bucket})
        return response
