import os
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from apps.accounts.models import User, Membership
from apps.organizations.models import OrganizationalUnit


class Command(BaseCommand):
    help = "Create fictitious local accounts; never resets existing passwords."

    @transaction.atomic
    def handle(self, *args, **options):
        password = os.getenv("DEMO_PASSWORD", "")
        if not password:
            raise CommandError("Set DEMO_PASSWORD externally.")
        try:
            validate_password(password)
        except ValidationError as error:
            raise CommandError("; ".join(error.messages)) from error
        units = []
        for code, name in [
            ("INST", "Instituição fictícia"),
            ("RISC", "Riscos"),
            ("COMP", "Compliance"),
            ("OPER", "Operações"),
        ]:
            unit, _ = OrganizationalUnit.objects.get_or_create(
                code=code, defaults={"name": name, "parent": units[0] if units else None}
            )
            units.append(unit)
        for name, role, count in [
            ("admin", None, 1),
            ("demandante", Membership.Role.REQUESTER, 3),
            ("demandado", Membership.Role.EXECUTOR, 6),
        ]:
            for i in range(count):
                username = name if role is None else f"{name}{i + 1}"
                user, created = User.objects.get_or_create(
                    username=username,
                    defaults={
                        "is_superuser": role is None,
                        "is_staff": role is None,
                        "first_name": username.capitalize(),
                    },
                )
                if created:
                    user.set_password(password)
                    user.save()
                if role:
                    Membership.objects.get_or_create(user=user, unit=units[1 + i % 3], role=role)
        self.stdout.write(self.style.SUCCESS("Foundation seed ready (fictitious users)."))
