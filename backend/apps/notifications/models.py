from django.conf import settings
from django.db import models
from django.utils import timezone
from apps.commitments.models import UUIDModel


class NotificationPolicy(UUIDModel):
    category = models.OneToOneField(
        "commitments.CommitmentCategory", null=True, blank=True, on_delete=models.PROTECT
    )
    definition = models.OneToOneField(
        "commitments.CommitmentDefinition", null=True, blank=True, on_delete=models.PROTECT
    )
    enabled = models.BooleanField(default=True)
    offsets = models.JSONField(default=list)
    basis = models.CharField(
        max_length=20,
        choices=[("calendar", "Dias corridos"), ("business", "Dias úteis")],
        default="calendar",
    )
    calendar = models.CharField(
        max_length=20,
        choices=[("national", "Nacional"), ("institution", "Nacional e institucional")],
        default="institution",
    )
    revision = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(category__isnull=False, definition__isnull=True)
                    | models.Q(category__isnull=True, definition__isnull=False)
                ),
                name="one_notification_policy_scope",
            )
        ]


class NotificationEvent(UUIDModel):
    key = models.CharField(max_length=240, unique=True)
    occurrence = models.ForeignKey(
        "commitments.CommitmentOccurrence",
        on_delete=models.PROTECT,
        related_name="notification_events",
    )
    kind = models.CharField(max_length=40)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    snapshot = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "id"]


class NotificationDelivery(UUIDModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        SENDING = "sending", "Envio em andamento"
        RETRY = "retry", "Retentativa agendada"
        ACCEPTED = "accepted", "Aceito pelo SMTP; entrega não confirmada"
        FAILED = "failed", "Falha definitiva"
        SKIPPED = "skipped", "Envio dispensado"
        UNKNOWN = "unknown", "Resultado do envio desconhecido"

    event = models.ForeignKey(
        NotificationEvent, on_delete=models.PROTECT, related_name="deliveries"
    )
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recipient_email = models.EmailField(blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    attempts = models.PositiveIntegerField(default=0)
    retry_limit = models.PositiveIntegerField(default=5)
    next_attempt_at = models.DateTimeField(default=timezone.now, db_index=True)
    lease_until = models.DateTimeField(null=True)
    accepted_at = models.DateTimeField(null=True)
    last_error = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["event", "recipient"], name="unique_event_recipient")
        ]
        indexes = [models.Index(fields=["status", "next_attempt_at"])]

    @property
    def message_id(self):
        return f"<{self.pk}@agenda.invalid>"


class NotificationAttempt(UUIDModel):
    delivery = models.ForeignKey(
        NotificationDelivery, on_delete=models.PROTECT, related_name="history"
    )
    number = models.PositiveIntegerField()
    recipient_email = models.EmailField(null=True, blank=True)
    stage = models.CharField(max_length=30)
    error_code = models.CharField(max_length=100, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class NotificationJob(models.Model):
    name = models.CharField(max_length=30, primary_key=True)
    last_success_at = models.DateTimeField(null=True)
    processed = models.PositiveIntegerField(default=0)
