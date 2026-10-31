from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from apps.accounts.models import Membership
from apps.accounts.permissions import has_role
from apps.audit.services import record
from .models import (
    IdentifierCounter,
    CommitmentDefinition,
    CommitmentOccurrence,
    CommitmentAssignment,
    OccurrenceVersion,
    ActionRecord,
    WorkflowTransition,
)


def can_manage(user, occurrence):
    definition = occurrence.definition
    return (
        definition.unit.active
        and has_role(user, definition.unit_id, Membership.Role.REQUESTER)
        and (user.is_superuser or definition.requester_id == user.pk)
    )


def can_execute(user, occurrence):
    return (
        user.is_active
        and occurrence.definition.unit.active
        and occurrence.assignments.filter(user=user).exists()
        and has_role(user, occurrence.definition.unit_id, Membership.Role.EXECUTOR)
    )


def available_transitions(user, occurrence, access=None):
    status = occurrence.status
    result = []
    manage, execute, assigned = (
        access
        if access is not None
        else (
            can_manage(user, occurrence),
            can_execute(user, occurrence),
            occurrence.assignments.filter(user=user).exists(),
        )
    )
    if execute:
        if status in ["pending", "rejected"]:
            result.append("start")
        if status == "in_progress":
            result.append("submit")
    if manage:
        if (
            status == "awaiting_validation"
            and occurrence.submitted_by_id != user.pk
            and not assigned
        ):
            result.extend(["approve", "reject"])
        if status not in ["completed", "cancelled"]:
            result.append("cancel")
        if status == "completed":
            result.append("reopen")
    return result


def snapshot(occurrence):
    return {
        "form_version": str(occurrence.form_version_id) if occurrence.form_version_id else None,
        "custom_values": occurrence.custom_values,
        "title": occurrence.title,
        "description": occurrence.description,
        "legal_basis": occurrence.legal_basis,
        "reference_date": occurrence.reference_date.isoformat(),
        "due_date": occurrence.due_date.isoformat(),
        "priority": occurrence.priority,
        "assignees": sorted(
            str(pk) for pk in occurrence.assignments.values_list("user_id", flat=True)
        ),
    }


def version(occurrence, actor):
    OccurrenceVersion.objects.create(
        occurrence=occurrence,
        revision=occurrence.revision,
        snapshot=snapshot(occurrence),
        actor=actor,
    )


def validate_assignees(unit, users):
    if not users or len({u.pk for u in users}) != len(users):
        raise ValidationError({"assignees": "Informe responsáveis únicos."})
    for user in users:
        if (
            not user.is_active
            or not unit.active
            or not Membership.objects.filter(
                user=user, unit=unit, role=Membership.Role.EXECUTOR
            ).exists()
        ):
            raise ValidationError(
                {"assignees": "Responsável sem perfil demandado ativo na unidade."}
            )


@transaction.atomic
def create_commitment(actor, data):
    values = dict(data)
    recurrence = values.pop("recurrence", None)
    unit = values["unit"]
    if not has_role(actor, unit.pk, Membership.Role.REQUESTER) or not unit.active:
        raise PermissionDenied("Sem permissão para criar nesta unidade.")
    from apps.customfields.models import FormVersion
    from apps.customfields.validation import validate_values
    from .models import CommitmentCategory

    # Same lock as publication: creation must use the currently published version.
    CommitmentCategory.objects.select_for_update().get(pk=values["category"].pk)
    form = FormVersion.objects.filter(category=values["category"]).order_by("revision").last()
    expected_form = values.pop("form_version", None)
    if form and str(expected_form) != str(form.pk):
        raise ValidationError(
            {"form_version": "Formulário publicado ou alterado. Recarregue a categoria."}
        )
    if not form and expected_form is not None:
        raise ValidationError({"form_version": "Formulário não pertence à categoria."})
    values["custom_values"] = validate_values(
        form, values.pop("custom_values", {}), unit, defaults=True
    )
    values["form_version"] = form
    assignees = values.pop("assignees")
    validate_assignees(unit, assignees)
    counter = IdentifierCounter.objects.select_for_update().get(name="commitment")
    counter.value += 1
    counter.save(update_fields=["value"])
    identifier = f"REG-{counter.value:06d}"
    occurrence_data = {k: values.pop(k) for k in ["reference_date", "due_date", "priority"]}
    definition = CommitmentDefinition.objects.create(
        identifier=identifier, requester=actor, **values
    )
    if recurrence:
        from .recurrence_services import initialize

        return initialize(actor, definition, recurrence, occurrence_data, assignees)
    occurrence = CommitmentOccurrence.objects.create(
        definition=definition,
        identifier=f"{identifier}/0001",
        title=definition.title,
        description=definition.description,
        legal_basis=definition.legal_basis,
        form_version=definition.form_version,
        custom_values=definition.custom_values,
        **occurrence_data,
    )
    CommitmentAssignment.objects.bulk_create(
        [CommitmentAssignment(occurrence=occurrence, user=user) for user in assignees]
    )
    version(occurrence, actor)
    record(
        actor,
        "commitment.created",
        definition,
        unit,
        after={"identifier": identifier, "occurrence": str(occurrence.pk), **snapshot(occurrence)},
    )
    from apps.notifications.services import emit

    emit(occurrence, "assigned", actor)
    return occurrence


@transaction.atomic
def update_occurrence(actor, occurrence, data):
    occurrence = CommitmentOccurrence.objects.select_for_update().get(pk=occurrence.pk)
    if not can_manage(actor, occurrence):
        raise PermissionDenied("Somente o demandante responsável pode editar.")
    if occurrence.status not in ["pending", "in_progress", "rejected"]:
        raise ValidationError(
            "Ocorrência bloqueada para edição; reabra a conclusão explicitamente."
        )
    values = dict(data)
    reason = values.pop("reason")
    expected = values.pop("revision")
    if expected != occurrence.revision:
        raise ValidationError("Registro alterado por outro usuário. Atualize a página.")
    before = snapshot(occurrence)
    if "custom_values" in values:
        from apps.customfields.validation import validate_values

        values["custom_values"] = validate_values(
            occurrence.form_version,
            values["custom_values"],
            occurrence.definition.unit,
            previous=occurrence.custom_values,
        )
    if "assignees" in values:
        users = values.pop("assignees")
        validate_assignees(occurrence.definition.unit, users)
        occurrence.assignments.all().delete()
        CommitmentAssignment.objects.bulk_create(
            [CommitmentAssignment(occurrence=occurrence, user=u) for u in users]
        )
    for key, value in values.items():
        setattr(occurrence, key, value)
    occurrence.revision += 1
    occurrence.save()
    version(occurrence, actor)
    record(
        actor,
        "occurrence.updated",
        occurrence,
        occurrence.definition.unit,
        before=before,
        after=snapshot(occurrence),
        reason=reason,
    )
    from apps.notifications.services import emit

    after = snapshot(occurrence)
    if before != after:
        emit(
            occurrence,
            "reassigned" if before["assignees"] != after["assignees"] else "changed",
            actor,
        )
    return occurrence


@transaction.atomic
def add_action(actor, occurrence, text, files=None):
    occurrence = CommitmentOccurrence.objects.select_for_update().get(pk=occurrence.pk)
    if not can_execute(actor, occurrence):
        raise PermissionDenied("Somente responsáveis atribuídos podem registrar providências.")
    if occurrence.status not in ["in_progress", "rejected"]:
        raise ValidationError("Inicie a execução antes de registrar providências.")
    if files:
        from django.conf import settings
        from django.db.models import Sum, Count
        from .models import Evidence

        used = Evidence.objects.filter(action__occurrence=occurrence).aggregate(
            size=Sum("size"), count=Count("pk")
        )
        if (
            used["count"] + len(files) > settings.EVIDENCE_MAX_OCCURRENCE_FILES
            or (used["size"] or 0) + sum(file["size"] for file in files)
            > settings.EVIDENCE_MAX_OCCURRENCE_BYTES
        ):
            raise ValidationError(
                {
                    "files": "Limite de anexos do compromisso atingido; retiradas lógicas também contam para a retenção."
                }
            )
    action = ActionRecord.objects.create(occurrence=occurrence, author=actor, text=text)
    record(
        actor,
        "action.created",
        action,
        occurrence.definition.unit,
        after={"occurrence": str(occurrence.pk), "text": text},
    )
    if files:
        from .evidence import store_files

        store_files(actor, action, files)
    return action


@transaction.atomic
def transition(actor, occurrence, operation, reason, expected):
    occurrence = CommitmentOccurrence.objects.select_for_update().get(pk=occurrence.pk)
    if expected != occurrence.revision:
        raise ValidationError("Registro alterado. Atualize antes de executar a ação.")
    if operation not in available_transitions(actor, occurrence):
        raise PermissionDenied("Transição indisponível para seu perfil ou estado atual.")
    if operation in ["reject", "cancel", "reopen"] and not reason.strip():
        raise ValidationError({"reason": "Justificativa obrigatória."})
    if operation == "submit":
        actions = occurrence.actions.all()
        boundary = (
            occurrence.transitions.filter(new_status__in=["rejected"])
            .order_by("-created_at")
            .first()
        )
        if boundary:
            actions = actions.filter(created_at__gt=boundary.created_at)
        if not actions.exists():
            raise ValidationError("Registre uma nova providência antes de submeter ou ressubmeter.")
    previous = occurrence.status
    target = {
        "start": "in_progress",
        "submit": "awaiting_validation",
        "approve": "completed",
        "reject": "rejected",
        "cancel": "cancelled",
        "reopen": "in_progress",
    }[operation]
    occurrence.status = target
    occurrence.revision += 1
    if operation == "submit":
        occurrence.submitted_by = actor
    if operation == "approve":
        occurrence.completed_at = timezone.now()
    if operation == "reopen":
        occurrence.completed_at = None
        occurrence.submitted_by = None
    occurrence.save()
    WorkflowTransition.objects.create(
        occurrence=occurrence,
        actor=actor,
        previous_status=previous,
        new_status=target,
        reason=reason,
    )
    record(
        actor,
        f"workflow.{operation}",
        occurrence,
        occurrence.definition.unit,
        before={"status": previous},
        after={"status": target},
        reason=reason,
    )
    from apps.notifications.services import emit

    kind = {
        "submit": "validation_requested",
        "approve": "approved",
        "reject": "rejected",
        "cancel": "cancelled",
        "reopen": "reopened",
    }.get(operation)
    if kind:
        emit(occurrence, kind, actor)
    return occurrence
