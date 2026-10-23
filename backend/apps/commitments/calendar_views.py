import json
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction, IntegrityError
from django.db.models import Count, F, Window
from django.db.models.functions import RowNumber
from rest_framework import generics, serializers, viewsets, mixins
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from drf_spectacular.utils import extend_schema, OpenApiParameter, inline_serializer
from apps.accounts.models import User
from .models import CommitmentOccurrence, SavedCalendarFilter
from .views import scoped_occurrences
from .serializers import PersonSerializer
from .calendar_filters import parse_filters, filter_occurrences, CalendarFilters


class CalendarEventSerializer(serializers.ModelSerializer):
    overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = CommitmentOccurrence
        fields = ["id", "identifier", "title", "due_date", "status", "priority", "overdue"]


class CalendarView(generics.GenericAPIView):
    serializer_class = CalendarEventSerializer

    @extend_schema(
        parameters=[CalendarFilters, OpenApiParameter("summary", bool)],
        responses=inline_serializer(
            name="CalendarResponse",
            fields={
                "date_start": serializers.DateField(),
                "date_end": serializers.DateField(),
                "total": serializers.IntegerField(),
                "days": serializers.ListField(child=serializers.DictField()),
            },
        ),
    )
    def get(self, request):
        filters = parse_filters(request.query_params, required_period=True)
        # Normalize scoped IDs before using window functions: joins must not duplicate events.
        ids = filter_occurrences(scoped_occurrences(request.user), filters).values("pk")
        qs = CommitmentOccurrence.objects.filter(pk__in=ids)
        days = {}
        for row in qs.order_by().values("due_date", "status").annotate(total=Count("pk")):
            key = row["due_date"].isoformat()
            day = days.setdefault(key, {"date": key, "total": 0, "status_counts": {}, "events": []})
            day["total"] += row["total"]
            day["status_counts"][row["status"]] = row["total"]
        summary = request.query_params.get("summary", "false")
        if summary not in ["true", "false"]:
            raise ValidationError({"summary": "Use true ou false."})
        if summary != "true":
            if (filters["date_end"] - filters["date_start"]).days > 61:
                raise ValidationError(
                    "Períodos detalhados limitados a 62 dias; use summary=true para o ano."
                )
            sample = (
                qs.annotate(
                    day_rank=Window(
                        expression=RowNumber(),
                        partition_by=[F("due_date")],
                        order_by=F("identifier").asc(),
                    )
                )
                .filter(day_rank__lte=3)
                .select_related(
                    "definition__unit",
                    "definition__entity",
                    "definition__category",
                    "definition__requester",
                )
                .prefetch_related("assignments__user")
                .order_by("due_date", "identifier")
            )
            for event in CalendarEventSerializer(sample, many=True).data:
                days[event["due_date"]]["events"].append(event)
        return Response(
            {
                "date_start": filters["date_start"],
                "date_end": filters["date_end"],
                "total": sum(day["total"] for day in days.values()),
                "days": [days[key] for key in sorted(days)],
            }
        )


class CalendarPeople(generics.GenericAPIView):
    serializer_class = PersonSerializer

    @extend_schema(
        responses=inline_serializer(
            name="CalendarPeopleResponse",
            fields={
                "requesters": PersonSerializer(many=True),
                "assignees": PersonSerializer(many=True),
            },
        )
    )
    def get(self, request):
        qs = scoped_occurrences(request.user)
        requester_ids = qs.values_list("definition__requester_id", flat=True)
        assignee_ids = qs.values_list("assignments__user_id", flat=True)
        return Response(
            {
                "requesters": PersonSerializer(
                    User.objects.filter(pk__in=requester_ids).order_by("username"), many=True
                ).data,
                "assignees": PersonSerializer(
                    User.objects.filter(pk__in=assignee_ids).order_by("username"), many=True
                ).data,
            }
        )


class SavedFilterSerializer(serializers.ModelSerializer):
    filters = serializers.JSONField()

    class Meta:
        model = SavedCalendarFilter
        fields = ["id", "name", "filters"]
        read_only_fields = ["id"]

    def validate_name(self, value):
        if SavedCalendarFilter.objects.filter(
            owner=self.context["request"].user, name=value
        ).exists():
            raise serializers.ValidationError("Já existe um favorito com este nome.")
        return value

    def validate_filters(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Filtros devem ser um objeto.")
        if set(value) - set(CalendarFilters().fields):
            raise serializers.ValidationError("Filtro não reconhecido.")
        # Store normalized strings/booleans, with identical validation to calendar requests.
        return json.loads(json.dumps(parse_filters(value), cls=DjangoJSONEncoder))


class SavedFilterView(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = SavedFilterSerializer
    lookup_value_regex = (
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    )

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return SavedCalendarFilter.objects.none()
        return SavedCalendarFilter.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        try:
            with transaction.atomic():
                serializer.save(owner=self.request.user)
        except IntegrityError:
            raise ValidationError({"name": "Já existe um favorito com este nome."})
