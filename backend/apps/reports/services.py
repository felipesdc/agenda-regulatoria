from datetime import timedelta
from django.db.models import (
    Count,
    Q,
    Avg,
    F,
    DurationField,
    ExpressionWrapper,
    OuterRef,
    Subquery,
    Prefetch,
    Exists,
)
from django.db.models.functions import TruncDate
from django.utils import timezone
from apps.commitments.models import WorkflowTransition, RecurrenceVersion, CommitmentAssignment
from apps.commitments.views import scoped_occurrences
from apps.commitments.calendar_filters import filter_occurrences

ACTIVE = ["pending", "in_progress", "awaiting_validation", "rejected"]


def cohort(user, filters):
    filters = dict(filters)
    assignee = filters.pop("assignee", None)
    qs = scoped_occurrences(user).select_related(None).prefetch_related(None)
    if assignee:
        qs = qs.alias(
            report_assigned=Exists(
                CommitmentAssignment.objects.filter(occurrence_id=OuterRef("pk"), user_id=assignee)
            )
        ).filter(report_assigned=True)
    # Scope and assignee use EXISTS; all remaining filters traverse singular FKs.
    # No join can duplicate a row, so avoid materializing/sorting all IDs.
    return filter_occurrences(qs, filters, deduplicate=False)


def counts(qs):
    today = timezone.localdate()
    return qs.aggregate(
        total=Count("pk"),
        pending=Count("pk", filter=Q(status="pending")),
        overdue=Count("pk", filter=Q(status__in=ACTIVE, due_date__lt=today)),
        due_next_seven=Count(
            "pk",
            filter=Q(
                status__in=ACTIVE, due_date__gte=today, due_date__lte=today + timedelta(days=7)
            ),
        ),
        awaiting_validation=Count("pk", filter=Q(status="awaiting_validation")),
        completed=Count("pk", filter=Q(status="completed")),
        cancelled=Count("pk", filter=Q(status="cancelled")),
        recurring=Count("pk", filter=~Q(periodicity="once")),
    )


def metrics(qs):
    today = timezone.localdate()
    qs = qs.annotate(
        completed_date=TruncDate("completed_at"),
        last_submit=Subquery(
            WorkflowTransition.objects.filter(
                occurrence_id=OuterRef("pk"),
                new_status="awaiting_validation",
                created_at__lte=OuterRef("completed_at"),
            )
            .order_by("-created_at", "-id")
            .values("created_at")[:1]
        ),
    )
    known = Q(status="completed", completed_at__isnull=False)
    duration = ExpressionWrapper(F("completed_at") - F("created_at"), output_field=DurationField())
    validation = ExpressionWrapper(
        F("completed_at") - F("last_submit"), output_field=DurationField()
    )
    data = qs.aggregate(
        total=Count("pk"),
        pending=Count("pk", filter=Q(status="pending")),
        overdue=Count("pk", filter=Q(status__in=ACTIVE, due_date__lt=today)),
        due_next_seven=Count(
            "pk",
            filter=Q(
                status__in=ACTIVE, due_date__gte=today, due_date__lte=today + timedelta(days=7)
            ),
        ),
        awaiting_validation=Count("pk", filter=Q(status="awaiting_validation")),
        completed=Count("pk", filter=Q(status="completed")),
        cancelled=Count("pk", filter=Q(status="cancelled")),
        recurring=Count("pk", filter=~Q(periodicity="once")),
        completed_known=Count("pk", filter=known),
        on_time=Count("pk", filter=known & Q(completed_date__lte=F("due_date"))),
        completion_samples=Count("pk", filter=known & Q(completed_at__gte=F("created_at"))),
        validation_samples=Count("pk", filter=known & Q(last_submit__isnull=False)),
        completion_duration=Avg(duration, filter=known & Q(completed_at__gte=F("created_at"))),
        validation_duration=Avg(validation, filter=known & Q(last_submit__isnull=False)),
    )
    data["on_time_percent"] = (
        round(100 * data["on_time"] / data["completed_known"], 2)
        if data["completed_known"]
        else None
    )
    for key in ["completion", "validation"]:
        value = data.pop(key + "_duration")
        data[key + "_mean_hours"] = (
            round(value.total_seconds() / 3600, 2) if value is not None else None
        )
    return data


def detailed(qs):
    return (
        qs.select_related(
            "definition__unit",
            "definition__entity",
            "definition__category",
            "definition__requester",
        )
        .prefetch_related(
            "assignments__user",
            Prefetch(
                "definition__recurrence_versions",
                queryset=RecurrenceVersion.objects.only("id", "definition_id", "revision"),
            ),
        )
        .defer(
            "custom_values",
            "definition__custom_values",
            "definition__description",
            "definition__legal_basis",
        )
        .order_by("due_date", "identifier")
    )
