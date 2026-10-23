from django.conf import settings
from django.db import models
from apps.commitments.models import UUIDModel


class CustomFieldDefinition(UUIDModel):
    key = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=160)
    kind = models.CharField(max_length=20)
    description = models.TextField(blank=True)
    required = models.BooleanField(default=False)
    default = models.JSONField(null=True, blank=True)
    rules = models.JSONField(default=dict)
    options = models.JSONField(default=list)
    order = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["order", "key"]


class FormVersion(UUIDModel):
    category = models.ForeignKey("commitments.CommitmentCategory", on_delete=models.PROTECT)
    revision = models.PositiveIntegerField()
    name = models.CharField(max_length=160)
    fields = models.JSONField(default=list)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["category_id", "-revision"]
        constraints = [
            models.UniqueConstraint(
                fields=["category", "revision"], name="unique_category_form_revision"
            )
        ]
