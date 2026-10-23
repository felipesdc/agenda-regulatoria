from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from apps.notifications.models import NotificationDelivery
from apps.notifications.recovery import hold_restored_outbox


class Command(BaseCommand):
    help = "Hold copied pending/retry/sending notices before resuming a restored environment."

    def add_arguments(self, parser):
        parser.add_argument("--expected-database", required=True)
        parser.add_argument("--reason", required=True)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            raise CommandError("Recuperação exige PostgreSQL.")
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            actual = cursor.fetchone()[0]
        if actual != options["expected_database"] or not actual.startswith(
            ("recovery_", "phase8_restore_", "phase8_tls_")
        ):
            raise CommandError(
                "Recusado: somente base nova recovery_* ou cópia descartável, com nome confirmado."
            )
        count = NotificationDelivery.objects.filter(
            status__in=["pending", "retry", "sending"]
        ).count()
        if not options["apply"]:
            self.stdout.write(f"Prévia: {count} avisos serão retidos; nenhuma alteração feita.")
            return
        count = hold_restored_outbox(options["reason"])
        self.stdout.write(
            f"{count} avisos retidos e auditados. Reconcilie Message-ID com SMTP antes de reprocessar."
        )
