from datetime import date, timedelta
from django.db import transaction
from django.db.models import Max
from rest_framework.exceptions import PermissionDenied, ValidationError
from apps.audit.services import record
from apps.accounts.models import User
from apps.accounts.permissions import has_role
from .models import (
    RecurrenceVersion,
    Holiday,
    CommitmentDefinition,
    CommitmentOccurrence,
    CommitmentAssignment,
)
from .recurrence_engine import scheduled_dates
from .services import snapshot, version, can_manage, update_occurrence, validate_assignees


def validated_dates(rule, through, holidays):
    try:
        return list(scheduled_dates(rule, through, holidays))
    except (ValueError, OverflowError) as exc:
        raise ValidationError("Calendário não permite gerar as datas solicitadas.") from exc


def holiday_snapshot(rule=None):
    qs = Holiday.objects.filter(active=True)
    if rule and rule["calendar"] == "national":
        qs = qs.filter(kind="national")
    return [d.isoformat() for d in qs.values_list("date", flat=True)]


def initialize(actor, definition, rule, occurrence_data, assignees):
    template = {
        "form_version": str(definition.form_version_id) if definition.form_version_id else None,
        "custom_values": definition.custom_values,
        "title": definition.title,
        "description": definition.description,
        "legal_basis": definition.legal_basis,
        "priority": occurrence_data["priority"],
        "reference_offset": (occurrence_data["reference_date"] - occurrence_data["due_date"]).days,
        "assignees": [str(u.pk) for u in assignees],
    }
    if abs(template["reference_offset"]) > 3652:
        raise ValidationError("Referência deve estar a até dez anos da data nominal.")
    if rule["start"] != occurrence_data["due_date"].isoformat():
        raise ValidationError("O início da recorrência deve coincidir com o vencimento informado.")
    rv = RecurrenceVersion.objects.create(
        definition=definition,
        revision=1,
        effective_from=rule["start"],
        rule=rule,
        holidays=holiday_snapshot(rule),
        template=template,
        actor=actor,
        reason="Criação da série",
    )
    generate(definition, date.fromisoformat(rule["end"]), actor)
    first = definition.occurrences.order_by("number").first()
    if not first:
        raise ValidationError("A regra não produz ocorrências no período informado.")
    record(actor, "series.created", rv, definition.unit, after={"rule": rule, "template": template})
    return first


@transaction.atomic
def generate(definition, through, actor):
    definition = CommitmentDefinition.objects.select_for_update().get(pk=definition.pk)
    if (
        not definition.unit.active
        or not has_role(actor, definition.unit_id, "requester")
        or (not actor.is_superuser and definition.requester_id != actor.pk)
    ):
        raise PermissionDenied("Autor sem permissão para gerar nesta unidade.")
    versions = list(definition.recurrence_versions.all())
    existing = set(
        definition.occurrences.exclude(scheduled_date=None).values_list("scheduled_date", flat=True)
    )
    number = definition.occurrences.aggregate(n=Max("number"))["n"] or 0
    created = 0
    for index, rv in enumerate(versions):
        end = (
            min(through, versions[index + 1].effective_from - timedelta(days=1))
            if index + 1 < len(versions)
            else through
        )
        users = list(User.objects.filter(pk__in=rv.template["assignees"]))
        dates = [
            (nominal, due)
            for nominal, due in validated_dates(rv.rule, end, rv.holidays)
            if nominal >= rv.effective_from and nominal not in existing
        ]
        if not dates:
            continue
        validate_assignees(definition.unit, users)
        if len(users) != len(rv.template["assignees"]):
            raise ValidationError("Responsáveis da série indisponíveis.")
        for nominal, due in dates:
            if number >= 1000:
                raise ValidationError("Limite de mil ocorrências por série; crie outra definição.")
            number += 1
            occurrence = CommitmentOccurrence.objects.create(
                definition=definition,
                number=number,
                identifier=f"{definition.identifier}/{number:04d}",
                scheduled_date=nominal,
                due_date=due,
                reference_date=nominal + timedelta(days=rv.template["reference_offset"]),
                form_version_id=rv.template.get("form_version"),
                custom_values=rv.template.get("custom_values", {}),
                recurrence_version=rv,
                periodicity=rv.rule["frequency"],
                **{k: rv.template[k] for k in ["title", "description", "legal_basis", "priority"]},
            )
            CommitmentAssignment.objects.bulk_create(
                [CommitmentAssignment(occurrence=occurrence, user=u) for u in users]
            )
            version(occurrence, actor)
            record(
                actor,
                "occurrence.generated",
                occurrence,
                definition.unit,
                after=snapshot(occurrence),
            )
            from apps.notifications.services import emit

            emit(occurrence, "assigned", actor)
            existing.add(nominal)
            created += 1
    return created


@transaction.atomic
def change_series(actor, occurrence, data):
    definition = CommitmentDefinition.objects.select_for_update().get(pk=occurrence.definition_id)
    occurrence = CommitmentOccurrence.objects.get(pk=occurrence.pk)
    if not can_manage(actor, occurrence):
        raise PermissionDenied("Somente o demandante responsável pode alterar a série.")
    latest = definition.recurrence_versions.order_by("revision").last()
    if not latest or data["revision"] != latest.revision:
        raise ValidationError("Versão da série alterada. Atualize a página.")
    template = {
        **latest.template,
        **{
            k: v
            for k, v in data.items()
            if k in ["title", "description", "legal_basis", "priority"]
        },
    }
    rule = data.get("rule", latest.rule)
    # New schedules start strictly after every materialized nominal date.
    last = definition.occurrences.aggregate(last=Max("scheduled_date"))["last"]
    effective = last + timedelta(days=1)
    if "rule" in data and date.fromisoformat(rule["start"]) < effective:
        raise ValidationError(
            "Nova regra deve iniciar após a última data nominal já gerada: " + last.isoformat()
        )
    if "rule" in data:
        effective = date.fromisoformat(rule["start"])
    holidays = holiday_snapshot(rule) if "rule" in data else latest.holidays
    if "rule" in data and not validated_dates(rule, date.fromisoformat(rule["end"]), holidays):
        raise ValidationError("Nova regra não produz ocorrências no período informado.")
    updated = []
    if data["scope"] == "pending":
        # Only untouched pending occurrences, from the selected nominal date onward.
        for target in (
            definition.occurrences.select_for_update()
            .filter(scheduled_date__gte=occurrence.scheduled_date, status="pending")
            .order_by("number")
        ):
            if target.actions.exists() or target.transitions.exists():
                continue
            update_occurrence(
                actor,
                target,
                {k: template[k] for k in ["title", "description", "legal_basis", "priority"]}
                | {"reason": data["reason"], "revision": target.revision},
            )
            updated.append(str(target.pk))
    rv = RecurrenceVersion.objects.create(
        definition=definition,
        revision=latest.revision + 1,
        effective_from=effective,
        rule=rule,
        holidays=holidays,
        template=template,
        actor=actor,
        reason=data["reason"],
    )
    record(
        actor,
        "series.updated",
        rv,
        definition.unit,
        before={"revision": latest.revision, "rule": latest.rule, "template": latest.template},
        after={
            "revision": rv.revision,
            "rule": rule,
            "template": template,
            "updated_pending": updated,
            "effective_from": effective.isoformat(),
        },
        reason=data["reason"],
    )
    if "rule" in data:
        generate(definition, date.fromisoformat(rule["end"]), actor)
    return rv
