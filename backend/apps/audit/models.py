import uuid
from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    operation = models.CharField(max_length=80)
    record_type = models.CharField(max_length=80)
    record_id = models.CharField(max_length=80, db_index=True)
    unit = models.ForeignKey(
        "organizations.OrganizationalUnit", null=True, on_delete=models.PROTECT
    )
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-occurred_at", "id"]
        indexes = [models.Index(fields=["unit", "occurred_at"])]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Audit events are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Audit events cannot be deleted.")
