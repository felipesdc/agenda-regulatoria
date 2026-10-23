from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from apps.accounts.models import User
from apps.audit.services import record


class Command(BaseCommand):
    help = "Configura somente e-mails fictícios ausentes para demonstração no Mailpit."

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG or settings.EMAIL_HOST != "mailpit":
            raise CommandError("Demonstração permitida somente em DEBUG com SMTP mailpit.")
        names = (
            ["admin"]
            + [f"demandante{i}" for i in range(1, 4)]
            + [f"demandado{i}" for i in range(1, 7)]
        )
        count = 0
        for user in User.objects.select_for_update().filter(username__in=names, email=""):
            user.email = f"{user.username}@agenda.invalid"
            user.save(update_fields=["email"])
            record(None, "user.demo_email_configured", user, after={"email": user.email})
            count += 1
        self.stdout.write(f"E-mails fictícios configurados: {count}; existentes preservados.")
