import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)


class Membership(models.Model):
    class Role(models.TextChoices):
        REQUESTER = "requester", "Demandante"
        EXECUTOR = "executor", "Demandado"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    unit = models.ForeignKey(
        "organizations.OrganizationalUnit", on_delete=models.PROTECT, related_name="memberships"
    )
    role = models.CharField(max_length=20, choices=Role.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "unit", "role"], name="unique_scoped_role")
        ]

    def __str__(self):
        return f"{self.user} / {self.unit} / {self.role}"
