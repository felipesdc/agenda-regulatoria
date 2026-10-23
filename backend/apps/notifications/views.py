from django.db import transaction
from django.db.models import Q, Count, Min
from rest_framework import generics, mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError, PermissionDenied, APIException
from drf_spectacular.utils import extend_schema, OpenApiParameter
from apps.accounts.models import User
from apps.accounts.permissions import IsAdministrator, has_role
from apps.audit.services import record
from apps.commitments.views import scoped_occurrences
from apps.commitments.models import CommitmentCategory, CommitmentDefinition
from .models import NotificationDelivery, NotificationPolicy, NotificationJob
from .serializers import (
    DeliverySerializer,
    RequeueInput,
    EmailInput,
    EmailOutput,
    PolicyInput,
    PolicyOutput,
    MonitorOutput,
    QueuedOutput,
)
from .services import requeue, policy_dict, DEFAULT_POLICY


class DeliveryView(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = DeliverySerializer

    def get_permissions(self):
        return [IsAdministrator()] if self.action == "requeue" else super().get_permissions()

    def get_queryset(self):
        qs = NotificationDelivery.objects.select_related(
            "event", "event__occurrence__definition__unit", "recipient"
        ).prefetch_related("history")
        if getattr(self, "swagger_fake_view", False):
            return qs.none()
        if not self.request.user.is_superuser:
            qs = qs.filter(
                recipient=self.request.user,
                event__occurrence__in=scoped_occurrences(self.request.user),
            )
        query = self.request.query_params.get("q", "")
        if len(query) > 200:
            raise ValidationError("Pesquisa limitada a 200 caracteres.")
        if query:
            qs = qs.filter(
                Q(event__snapshot__title__icontains=query)
                | Q(event__snapshot__identifier__icontains=query)
            )
        status = self.request.query_params.get("status", "")
        if status:
            if status not in NotificationDelivery.Status.values:
                raise ValidationError("Situação de envio inválida.")
            qs = qs.filter(status=status)
        occurrence = self.request.query_params.get("occurrence", "")
        if occurrence:
            from uuid import UUID

            try:
                UUID(occurrence)
            except ValueError as exc:
                raise ValidationError("Ocorrência inválida.") from exc
            qs = qs.filter(event__occurrence_id=occurrence)
        return qs

    @extend_schema(
        parameters=[
            OpenApiParameter("status", str),
            OpenApiParameter("occurrence", str),
            OpenApiParameter("q", str),
        ]
    )
    def list(self, *args, **kwargs):
        return super().list(*args, **kwargs)

    @extend_schema(request=RequeueInput, responses=DeliverySerializer)
    @action(detail=True, methods=["post"])
    def requeue(self, request, pk=None):
        delivery = self.get_object()
        serializer = RequeueInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        if (
            delivery.status == "unknown"
            and not serializer.validated_data["acknowledge_duplicate_risk"]
        ):
            raise ValidationError(
                "Confirme o risco de duplicidade antes de repetir um resultado desconhecido."
            )
        delivery = requeue(
            delivery.pk,
            request.user,
            serializer.validated_data["reason"],
            serializer.validated_data["acknowledge_duplicate_risk"],
        )
        return Response(self.get_serializer(delivery).data)


class EmailView(generics.GenericAPIView):
    serializer_class = EmailInput

    @extend_schema(responses=EmailOutput)
    def get(self, request):
        return Response({"email": User.objects.only("email").get(pk=request.user.pk).email})

    @extend_schema(request=EmailInput, responses=EmailOutput)
    @transaction.atomic
    def patch(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.select_for_update().get(pk=request.user.pk)
        before = {"email": user.email}
        user.email = serializer.validated_data["email"]
        user.save(update_fields=["email"])
        record(
            user,
            "user.notification_email_updated",
            user,
            before=before,
            after={"email": user.email},
        )
        return Response({"email": user.email})


class PolicyView(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = PolicyOutput

    def get_queryset(self):
        qs = NotificationPolicy.objects.select_related("category", "definition")
        if getattr(self, "swagger_fake_view", False):
            return qs.none()
        if not self.request.user.is_superuser:
            units = self.request.user.memberships.filter(
                role="requester", unit__active=True
            ).values_list("unit_id", flat=True)
            qs = qs.filter(
                Q(category__isnull=False)
                | Q(definition__requester=self.request.user, definition__unit_id__in=units)
            )
        return qs

    @extend_schema(request=PolicyInput, responses=PolicyOutput)
    def create(self, request):
        serializer = PolicyInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        definition, category = data.pop("definition", None), data.pop("category", None)
        if category and not request.user.is_superuser:
            raise PermissionDenied("Políticas de categoria exigem administrador global.")
        if definition and (
            not has_role(request.user, definition.unit_id, "requester")
            or (not request.user.is_superuser and definition.requester_id != request.user.pk)
        ):
            raise PermissionDenied("Sem permissão para configurar este compromisso.")
        reason, expected = data.pop("reason"), data.pop("revision")
        with transaction.atomic():
            # Lock a stable parent, even when no policy exists yet.
            if definition:
                CommitmentDefinition.objects.select_for_update().get(pk=definition.pk)
            else:
                CommitmentCategory.objects.select_for_update().get(pk=category.pk)
            policy = NotificationPolicy.objects.filter(
                definition=definition, category=category
            ).first()
            if expected != (policy.revision if policy else 0):
                raise ValidationError("Política alterada. Atualize a lista antes de salvar.")
            before = policy_dict(policy) if policy else DEFAULT_POLICY
            if not policy:
                policy = NotificationPolicy(definition=definition, category=category)
            for key, value in data.items():
                setattr(policy, key, value)
            policy.revision = expected + 1
            policy.save()
            record(
                request.user,
                "notification.policy_updated",
                policy,
                definition.unit if definition else None,
                before=before,
                after=policy_dict(policy),
                reason=reason,
            )
        return Response(PolicyOutput(policy).data, status=200)


class MonitorView(generics.GenericAPIView):
    permission_classes = [IsAdministrator]
    serializer_class = MonitorOutput

    def get(self, request):
        counts = {
            row["status"]: row["total"]
            for row in NotificationDelivery.objects.values("status").annotate(total=Count("pk"))
        }
        oldest = NotificationDelivery.objects.filter(status__in=["pending", "retry"]).aggregate(
            value=Min("created_at")
        )["value"]
        return Response(
            {
                "counts": counts,
                "oldest_pending_at": oldest,
                "jobs": list(
                    NotificationJob.objects.values("name", "last_success_at", "processed")
                ),
            }
        )


class RunJobsView(generics.GenericAPIView):
    permission_classes = [IsAdministrator]
    serializer_class = QueuedOutput

    @extend_schema(request=None, responses=QueuedOutput)
    def post(self, request):
        from .tasks import dispatch, deadlines

        try:
            deadlines.delay()
            dispatch.delay()
        except Exception as exc:
            error = APIException(
                "Fila indisponível. Os eventos permanecem no banco para reprocessamento automático."
            )
            error.status_code = 503
            raise error from exc
        return Response({"queued": True}, status=202)
