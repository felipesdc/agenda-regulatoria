import logging
from datetime import timedelta
from urllib.parse import urlencode
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.core.validators import validate_email
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError, PermissionDenied
from apps.accounts.permissions import has_role
from apps.audit.services import record
from apps.commitments.models import CommitmentOccurrence, Holiday
from apps.commitments.recurrence_engine import business_day
from .models import (
    NotificationEvent,
    NotificationDelivery,
    NotificationAttempt,
    NotificationPolicy,
    NotificationJob,
)

logger = logging.getLogger(__name__)
KINDS = {
    "assigned": "Novo compromisso atribuído",
    "changed": "Compromisso alterado",
    "reassigned": "Responsabilidade alterada",
    "validation_requested": "Validação solicitada",
    "approved": "Conclusão validada",
    "rejected": "Conclusão rejeitada",
    "cancelled": "Compromisso cancelado",
    "reopened": "Compromisso reaberto",
    "deadline": "Alerta de vencimento",
}
DEFAULT_POLICY = {
    "enabled": True,
    "offsets": [30, 15, 7, 3, 1, 0, -1],
    "basis": "calendar",
    "calendar": "institution",
    "revision": 0,
}


def wake_outbox():
    # Best-effort acceleration only. The database outbox + Beat recovers broker outages.
    from .tasks import dispatch

    try:
        dispatch.delay()
    except Exception:
        logger.warning("notification_broker_unavailable; durable outbox retained")


@transaction.atomic
def emit(occurrence, kind, actor=None, key=None, extra=None):
    key = key or f"{occurrence.pk}:{occurrence.revision}:{kind}"
    if kind not in KINDS:
        raise ValueError("Unknown notification kind")
    snap = {
        "identifier": occurrence.identifier,
        "title": occurrence.title,
        "description": occurrence.description[:240],
        "due_date": occurrence.due_date.isoformat(),
        "status": occurrence.status,
        "responsible": list(occurrence.assignments.values_list("user__username", flat=True)),
        "revision": occurrence.revision,
        **(extra or {}),
    }
    event, created = NotificationEvent.objects.get_or_create(
        key=key, defaults={"occurrence": occurrence, "kind": kind, "actor": actor, "snapshot": snap}
    )
    if not created:
        return event
    recipients = {a.user_id: a.user for a in occurrence.assignments.select_related("user")}
    if kind != "assigned":
        recipients[occurrence.definition.requester_id] = occurrence.definition.requester
    if kind == "validation_requested":
        recipients = {occurrence.definition.requester_id: occurrence.definition.requester}
    NotificationDelivery.objects.bulk_create(
        [NotificationDelivery(event=event, recipient=u) for u in recipients.values()]
    )
    record(
        actor,
        "notification.event_created",
        event,
        occurrence.definition.unit,
        after={"kind": kind, "key": key, "recipients": [str(u.pk) for u in recipients.values()]},
    )
    return event


def event_label(event):
    if event.kind == "deadline":
        offset = event.snapshot.get("offset", 0)
        return (
            "Vencimento próximo"
            if offset > 0
            else "Compromisso atrasado"
            if offset < 0
            else "Vencimento no dia"
        )
    return KINDS[event.kind]


def current_access(delivery):
    occurrence, user = delivery.event.occurrence, delivery.recipient
    definition = occurrence.definition
    if not user.is_active or not definition.unit.active:
        return False
    if definition.requester_id == user.pk and has_role(user, definition.unit_id, "requester"):
        return True
    return (
        has_role(user, definition.unit_id, "executor")
        and occurrence.assignments.filter(user=user).exists()
    )


def skip_reason(delivery):
    if not current_access(delivery):
        return "recipient_no_longer_authorized"
    occurrence = delivery.event.occurrence
    if delivery.event.kind == "deadline" and (
        occurrence.status in ["completed", "cancelled"]
        or occurrence.due_date.isoformat() != delivery.event.snapshot["due_date"]
    ):
        return "obsolete_deadline"
    if delivery.event.kind == "validation_requested" and (
        occurrence.status != "awaiting_validation"
        or occurrence.revision != delivery.event.snapshot["revision"]
    ):
        return "obsolete_validation_request"
    if delivery.event.kind == "deadline":
        policy = (
            NotificationPolicy.objects.filter(definition=occurrence.definition).first()
            or NotificationPolicy.objects.filter(
                category_id=occurrence.definition.category_id
            ).first()
        )
        current = policy_dict(policy) if policy else DEFAULT_POLICY
        original = delivery.event.snapshot.get("policy", DEFAULT_POLICY)
        if (
            not current["enabled"]
            or delivery.event.snapshot.get("offset", 0) not in current["offsets"]
            or any(current[k] != original[k] for k in ["basis", "calendar"])
        ):
            return "obsolete_deadline_policy"
    try:
        validate_email(delivery.recipient.email)
    except DjangoValidationError:
        return "recipient_email_missing_or_invalid"
    return ""


def attempt(delivery, stage, error="", actor=None, reason=""):
    NotificationAttempt.objects.create(
        delivery=delivery,
        number=delivery.attempts,
        recipient_email=delivery.recipient_email
        if stage in ["started", "accepted", "retry", "failed", "unknown"]
        else None,
        stage=stage,
        error_code=error,
        actor=actor,
        reason=reason,
    )


def set_result(delivery, status, error=""):
    delivery.status = status
    delivery.last_error = error
    delivery.lease_until = None
    if status == "accepted":
        delivery.accepted_at = timezone.now()
    delivery.save()
    attempt(delivery, status, error)
    record(
        None,
        "notification." + status,
        delivery,
        delivery.event.occurrence.definition.unit,
        after={
            "event": str(delivery.event_id),
            "attempt": delivery.attempts,
            "status": status,
            "error_code": error,
            "message_id": delivery.message_id,
            "recipient_email": delivery.recipient_email,
        },
    )


@transaction.atomic
def claim(delivery_id):
    delivery = NotificationDelivery.objects.select_for_update().filter(pk=delivery_id).first()
    if (
        not delivery
        or delivery.status not in ["pending", "retry"]
        or delivery.next_attempt_at > timezone.now()
    ):
        return None
    reason = skip_reason(delivery)
    if reason:
        set_result(delivery, "skipped", reason)
        return None
    delivery.status = "sending"
    delivery.attempts += 1
    delivery.recipient_email = delivery.recipient.email
    delivery.lease_until = timezone.now() + timedelta(seconds=settings.NOTIFICATION_LEASE_SECONDS)
    delivery.save()
    attempt(delivery, "started")
    return delivery


@transaction.atomic
def finish(delivery_id, number, status, error=""):
    delivery = NotificationDelivery.objects.select_for_update().get(pk=delivery_id)
    if delivery.status not in ["sending", "unknown"] or delivery.attempts != number:
        return
    if status == "retry":
        if number >= delivery.retry_limit:
            status = "failed"
        else:
            delivery.next_attempt_at = timezone.now() + timedelta(
                seconds=min(
                    3600,
                    settings.NOTIFICATION_RETRY_BASE_SECONDS
                    * 2
                    ** (
                        max(1, number - (delivery.retry_limit - settings.NOTIFICATION_MAX_ATTEMPTS))
                        - 1
                    ),
                )
            )
    set_result(delivery, status, error)


@transaction.atomic
def recover_expired(delivery_id):
    delivery = NotificationDelivery.objects.select_for_update().get(pk=delivery_id)
    if (
        delivery.status == "sending"
        and delivery.lease_until
        and delivery.lease_until <= timezone.now()
    ):
        set_result(delivery, "unknown", "worker_lease_expired")
        return True
    return False


@transaction.atomic
def requeue(delivery_id, actor, reason, acknowledge_duplicate_risk=False):
    delivery = NotificationDelivery.objects.select_for_update().get(pk=delivery_id)
    if delivery.status not in ["failed", "unknown", "skipped"]:
        raise ValidationError(
            "Somente falhas, dispensados ou resultados desconhecidos podem ser reprocessados."
        )
    if not actor.is_active or not actor.is_superuser:
        raise PermissionDenied("Reprocessamento exige administrador global.")
    if delivery.status == "unknown" and not acknowledge_duplicate_risk:
        raise ValidationError("Confirme o risco de duplicidade para resultado desconhecido.")
    before = {"status": delivery.status, "attempts": delivery.attempts}
    delivery.status = "pending"
    delivery.retry_limit = delivery.attempts + settings.NOTIFICATION_MAX_ATTEMPTS
    delivery.next_attempt_at = timezone.now()
    delivery.last_error = ""
    delivery.save()
    attempt(delivery, "manual_requeue", actor=actor, reason=reason)
    record(
        actor,
        "notification.requeued",
        delivery,
        delivery.event.occurrence.definition.unit,
        before=before,
        after={"status": "pending"},
        reason=reason,
    )
    transaction.on_commit(wake_outbox, robust=True)
    return delivery


def alert_date(due, offset, basis, holidays):
    if basis == "calendar" or offset == 0:
        return due - timedelta(days=offset)
    day, remaining = due, abs(offset)
    step = -1 if offset > 0 else 1
    for _ in range(1460):
        day += timedelta(days=step)
        if business_day(day, holidays):
            remaining -= 1
            if remaining == 0:
                return day
    raise ValueError("No business date within bounded calendar")


def policy_dict(policy):
    return {field: getattr(policy, field) for field in DEFAULT_POLICY}


def scan_deadlines(today=None):
    today = today or timezone.localdate()
    policies = list(NotificationPolicy.objects.all())
    definitions = {p.definition_id: policy_dict(p) for p in policies if p.definition_id}
    categories = {p.category_id: policy_dict(p) for p in policies if p.category_id}
    national = {
        d.isoformat()
        for d in Holiday.objects.filter(active=True, kind="national").values_list("date", flat=True)
    }
    institutional = national | {
        d.isoformat()
        for d in Holiday.objects.filter(active=True, kind="institution").values_list(
            "date", flat=True
        )
    }
    configurations = [DEFAULT_POLICY] + list(definitions.values()) + list(categories.values())
    calendar_bound = max(
        (
            abs(n)
            for p in configurations
            if p["enabled"] and p["basis"] == "calendar"
            for n in p["offsets"]
        ),
        default=0,
    )
    business_offsets = [
        abs(n)
        for p in configurations
        if p["enabled"] and p["basis"] == "business"
        for n in p["offsets"]
    ]
    business_bound = (
        min(1460, (max(business_offsets) + len(institutional)) * 7 // 5 + 14)
        if business_offsets
        else 0
    )
    bound = max(calendar_bound, business_bound)
    qs = CommitmentOccurrence.objects.filter(
        definition__unit__active=True,
        due_date__range=(
            today - timedelta(days=bound + settings.NOTIFICATION_ALERT_CATCHUP_DAYS),
            today + timedelta(days=bound),
        ),
    ).exclude(status__in=["completed", "cancelled"])
    created = 0
    for pk in qs.values_list("pk", flat=True).iterator(chunk_size=200):
        with transaction.atomic():
            occurrence = (
                CommitmentOccurrence.objects.select_for_update(of=("self",))
                .select_related("definition__unit", "definition__requester")
                .get(pk=pk)
            )
            if (
                occurrence.status in ["completed", "cancelled"]
                or not occurrence.definition.unit.active
            ):
                continue
            policy = definitions.get(
                occurrence.definition_id,
                categories.get(occurrence.definition.category_id, DEFAULT_POLICY),
            )
            if not policy["enabled"]:
                continue
            holidays = national if policy["calendar"] == "national" else institutional
            for offset in policy["offsets"]:
                try:
                    target = alert_date(occurrence.due_date, offset, policy["basis"], holidays)
                except ValueError:
                    logger.error("notification_calendar_blocked occurrence=%s", pk)
                    continue
                if (
                    not today - timedelta(days=settings.NOTIFICATION_ALERT_CATCHUP_DAYS)
                    <= target
                    <= today
                ):
                    continue
                if target < today and offset > 0 and occurrence.due_date <= today:
                    continue
                key = f"deadline:{pk}:{occurrence.due_date}:{offset}:{policy['basis']}:{policy['calendar']}"
                if NotificationEvent.objects.filter(key=key).exists():
                    continue
                emit(
                    occurrence,
                    "deadline",
                    key=key,
                    extra={
                        "offset": offset,
                        "alert_date": target.isoformat(),
                        "policy": policy,
                        "holidays": sorted(holidays),
                    },
                )
                created += 1
    NotificationJob.objects.update_or_create(
        name="deadlines", defaults={"last_success_at": timezone.now(), "processed": created}
    )
    return created


def internal_link(event):
    return (
        settings.NOTIFICATION_BASE_URL + "/?" + urlencode({"occurrence": str(event.occurrence_id)})
    )
