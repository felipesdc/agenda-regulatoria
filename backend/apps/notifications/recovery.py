from django.db import transaction
from rest_framework.exceptions import ValidationError
from apps.audit.services import record
from .models import NotificationDelivery
from .services import attempt


@transaction.atomic
def hold_restored_outbox(reason):
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 4000:
        raise ValidationError("Justificativa de recuperação obrigatória, até 4000 caracteres.")
    count = 0
    for delivery in (
        NotificationDelivery.objects.select_for_update()
        .filter(status__in=["pending", "retry", "sending"])
        .select_related("event__occurrence__definition__unit")
    ):
        before = {"status": delivery.status, "attempts": delivery.attempts}
        delivery.status = "unknown"
        delivery.lease_until = None
        delivery.last_error = "restore_reconciliation_required"
        delivery.save()
        attempt(delivery, "recovery_hold", error=delivery.last_error, reason=reason)
        record(
            None,
            "notification.recovery_hold",
            delivery,
            delivery.event.occurrence.definition.unit,
            before=before,
            after={"status": "unknown", "message_id": delivery.message_id},
            reason=reason,
        )
        count += 1
    return count
