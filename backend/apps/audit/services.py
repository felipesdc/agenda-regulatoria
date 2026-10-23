from .models import AuditEvent


def record(actor, operation, obj, unit=None, before=None, after=None, reason=""):
    return AuditEvent.objects.create(
        actor=actor,
        operation=operation,
        record_type=obj._meta.label_lower,
        record_id=str(obj.pk),
        unit=unit,
        before=before or {},
        after=after or {},
        reason=reason,
    )
