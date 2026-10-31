import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class RegulatoryEntity(UUIDModel):
    name = models.CharField(max_length=160, unique=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]


class CommitmentCategory(UUIDModel):
    name = models.CharField(max_length=160, unique=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]


class IdentifierCounter(models.Model):
    name = models.CharField(max_length=30, primary_key=True)
    value = models.PositiveBigIntegerField(default=0)


class CommitmentDefinition(UUIDModel):
    form_version = models.ForeignKey(
        "customfields.FormVersion", null=True, on_delete=models.PROTECT
    )
    custom_values = models.JSONField(default=dict)
    identifier = models.CharField(max_length=30, unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField()
    legal_basis = models.TextField(blank=True)
    entity = models.ForeignKey(RegulatoryEntity, on_delete=models.PROTECT)
    category = models.ForeignKey(CommitmentCategory, on_delete=models.PROTECT)
    unit = models.ForeignKey("organizations.OrganizationalUnit", on_delete=models.PROTECT)
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "id"]


class CommitmentOccurrence(UUIDModel):
    form_version = models.ForeignKey(
        "customfields.FormVersion", null=True, on_delete=models.PROTECT
    )
    custom_values = models.JSONField(default=dict)

    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        IN_PROGRESS = "in_progress", "Em andamento"
        AWAITING = "awaiting_validation", "Aguardando validação"
        COMPLETED = "completed", "Concluído"
        REJECTED = "rejected", "Rejeitado"
        CANCELLED = "cancelled", "Cancelado"

    definition = models.ForeignKey(
        CommitmentDefinition, on_delete=models.PROTECT, related_name="occurrences"
    )
    scheduled_date = models.DateField(null=True, db_index=True)
    recurrence_version = models.ForeignKey("RecurrenceVersion", null=True, on_delete=models.PROTECT)
    periodicity = models.CharField(max_length=20, default="once", db_index=True)
    number = models.PositiveIntegerField(default=1)
    identifier = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField()
    legal_basis = models.TextField(blank=True)
    reference_date = models.DateField()
    due_date = models.DateField(db_index=True)
    priority = models.CharField(
        max_length=10,
        choices=[("low", "Baixa"), ("normal", "Normal"), ("high", "Alta"), ("critical", "Crítica")],
        default="normal",
    )
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING)
    revision = models.PositiveIntegerField(default=1)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.PROTECT,
        related_name="submitted_occurrences",
    )
    completed_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_date", "identifier"]
        constraints = [
            models.UniqueConstraint(
                fields=["definition", "scheduled_date"], name="unique_series_date"
            ),
            models.UniqueConstraint(
                fields=["definition", "number"], name="unique_definition_occurrence"
            ),
            models.CheckConstraint(
                condition=models.Q(number__gte=1), name="positive_occurrence_number"
            ),
            models.CheckConstraint(
                condition=models.Q(
                    status__in=[
                        "pending",
                        "in_progress",
                        "awaiting_validation",
                        "completed",
                        "rejected",
                        "cancelled",
                    ]
                ),
                name="valid_occurrence_status",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "due_date"]),
            models.Index(fields=["due_date", "identifier"]),
            models.Index(fields=["status", "completed_at"]),
        ]

    @property
    def overdue(self):
        return self.due_date < timezone.localdate() and self.status not in [
            self.Status.COMPLETED,
            self.Status.CANCELLED,
        ]


class CommitmentAssignment(models.Model):
    occurrence = models.ForeignKey(
        CommitmentOccurrence, on_delete=models.PROTECT, related_name="assignments"
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["occurrence", "user"], name="unique_occurrence_executor"
            )
        ]


class OccurrenceVersion(UUIDModel):
    occurrence = models.ForeignKey(
        CommitmentOccurrence, on_delete=models.PROTECT, related_name="versions"
    )
    revision = models.PositiveIntegerField()
    snapshot = models.JSONField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["revision"]
        constraints = [
            models.UniqueConstraint(
                fields=["occurrence", "revision"], name="unique_occurrence_version"
            )
        ]


class ActionRecord(UUIDModel):
    occurrence = models.ForeignKey(
        CommitmentOccurrence, on_delete=models.PROTECT, related_name="actions"
    )
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class WorkflowTransition(UUIDModel):
    occurrence = models.ForeignKey(
        CommitmentOccurrence, on_delete=models.PROTECT, related_name="transitions"
    )
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    previous_status = models.CharField(max_length=30)
    new_status = models.CharField(max_length=30)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["occurrence", "new_status", "-created_at"])]


class SavedCalendarFilter(UUIDModel):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=80)
    filters = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "name"], name="unique_user_calendar_filter")
        ]


class Holiday(UUIDModel):
    kind = models.CharField(
        max_length=20,
        choices=[("national", "Nacional"), ("institution", "Institucional")],
        default="institution",
    )
    date = models.DateField(unique=True)
    name = models.CharField(max_length=160)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["date"]


class RecurrenceVersion(UUIDModel):
    definition = models.ForeignKey(
        CommitmentDefinition, on_delete=models.PROTECT, related_name="recurrence_versions"
    )
    revision = models.PositiveIntegerField()
    effective_from = models.DateField()
    rule = models.JSONField()
    holidays = models.JSONField(default=list)
    template = models.JSONField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["revision"]
        constraints = [
            models.UniqueConstraint(
                fields=["definition", "revision"], name="unique_recurrence_revision"
            )
        ]


class EvidenceBlob(UUIDModel):
    # Private content is part of the PostgreSQL transaction and normal backups.
    content = models.BinaryField()


class Evidence(UUIDModel):
    action = models.ForeignKey(ActionRecord, on_delete=models.PROTECT, related_name="evidence")
    filename = models.CharField(max_length=180)
    media_type = models.CharField(max_length=120)
    size = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    storage_key = models.CharField(max_length=200, unique=True)
    storage_backend = models.CharField(max_length=200)
    inspection = models.CharField(max_length=250)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at", "id"]


class EvidenceWithdrawal(UUIDModel):
    evidence = models.OneToOneField(Evidence, on_delete=models.PROTECT, related_name="withdrawal")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.CharField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)
