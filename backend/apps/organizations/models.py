import uuid
from django.core.exceptions import ValidationError
from django.db import models


class OrganizationalUnit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160)
    code = models.CharField(max_length=30, unique=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="children"
    )
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(id=models.F("parent_id")), name="unit_not_own_parent"
            )
        ]

    def clean(self):
        super().clean()
        seen = {self.pk}
        parent = self.parent
        while parent:
            if parent.pk in seen:
                raise ValidationError({"parent": "A hierarquia não pode conter ciclos."})
            seen.add(parent.pk)
            parent = parent.parent

    def __str__(self):
        return self.name
