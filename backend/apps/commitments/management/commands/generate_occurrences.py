from datetime import date
from django.core.management.base import BaseCommand, CommandError
from rest_framework.exceptions import ValidationError, PermissionDenied
from apps.commitments.models import CommitmentDefinition
from apps.commitments.recurrence_services import generate


class Command(BaseCommand):
    help = "Gera ocorrências idempotentemente até uma data, respeitando versões e escopo ativo."

    def add_arguments(self, parser):
        parser.add_argument("--through", required=True, help="AAAA-MM-DD")

    def handle(self, *args, **options):
        try:
            through = date.fromisoformat(options["through"])
        except ValueError as exc:
            raise CommandError("Data inválida; use AAAA-MM-DD.") from exc
        created, failed = 0, 0
        for definition in (
            CommitmentDefinition.objects.filter(
                unit__active=True, recurrence_versions__isnull=False
            )
            .distinct()
            .iterator()
        ):
            latest = definition.recurrence_versions.select_related("actor").last()
            if not latest.actor.is_active:
                failed += 1
                self.stderr.write(
                    f"{definition.identifier}: autor da versão inativo; revise a série."
                )
                continue
            try:
                created += generate(definition, through, latest.actor)
            except (ValidationError, PermissionDenied):
                failed += 1
                self.stderr.write(
                    f"{definition.identifier}: geração bloqueada; revise responsáveis e limites."
                )
        self.stdout.write(f"Ocorrências criadas: {created}; séries bloqueadas: {failed}.")
        if failed:
            raise CommandError("Algumas séries requerem revisão; as demais foram processadas.")
