from datetime import timedelta
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from apps.accounts.models import User
from apps.organizations.models import OrganizationalUnit
from apps.commitments.models import RegulatoryEntity, CommitmentCategory, CommitmentDefinition
from apps.commitments.services import create_commitment
from apps.audit.services import record


class Command(BaseCommand):
    help = "Idempotent fictitious phase-2 catalogs and commitments. Run seed_foundation first."

    @transaction.atomic
    def handle(self, *args, **kwargs):
        admin = User.objects.filter(username="admin", is_superuser=True, is_active=True).first()
        if not admin:
            raise CommandError("Run seed_foundation first.")
        entities = []
        for name in [
            "Banco Central — exemplo fictício",
            "CVM — exemplo fictício",
            "Receita Federal — exemplo fictício",
            "Controle interno — exemplo fictício",
            "Autorregulação — exemplo fictício",
        ]:
            obj, created = RegulatoryEntity.objects.get_or_create(name=name)
            if created:
                record(admin, "catalog.created", obj, after={"name": name, "fictitious": True})
            entities.append(obj)
        category, created = CommitmentCategory.objects.get_or_create(
            name="Demonstração institucional"
        )
        if created:
            record(admin, "catalog.created", category, after={"name": category.name})
        for i, code in enumerate(["RISC", "COMP", "OPER"]):
            unit = OrganizationalUnit.objects.get(code=code)
            requester = User.objects.get(username=f"demandante{i + 1}")
            executor = User.objects.get(username=f"demandado{i + 1}")
            title = f"Exemplo fictício — conferência institucional {code}"
            if not CommitmentDefinition.objects.filter(title=title, unit=unit).exists():
                create_commitment(
                    requester,
                    {
                        "title": title,
                        "description": "Dados de demonstração. Não representa obrigação regulatória real.",
                        "legal_basis": "Exemplo sem validade normativa",
                        "unit": unit,
                        "entity": entities[i],
                        "category": category,
                        "assignees": [executor],
                        "reference_date": timezone.localdate(),
                        "due_date": timezone.localdate() + timedelta(days=7),
                        "priority": "normal",
                    },
                )
        self.stdout.write(self.style.SUCCESS("Phase-2 fictitious seed ready."))
