import uuid
from django.db import transaction, IntegrityError
from django.db.models import OuterRef, Subquery
from rest_framework import mixins, viewsets, generics
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError, PermissionDenied
from drf_spectacular.utils import extend_schema, OpenApiParameter
from apps.accounts.permissions import IsAdministrator, has_role
from apps.accounts.models import User
from apps.commitments.models import CommitmentCategory
from apps.commitments.serializers import PersonSerializer
from apps.organizations.models import OrganizationalUnit
from apps.audit.services import record
from .models import CustomFieldDefinition, FormVersion
from .serializers import FieldInput, FieldOutput, FormInput, FormOutput


class FieldView(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = CustomFieldDefinition.objects.all()
    serializer_class = FieldOutput
    permission_classes = [IsAdministrator]

    @extend_schema(request=FieldInput, responses={201: FieldOutput})
    @transaction.atomic
    def create(self, request):
        serializer = FieldInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        reason = data.pop("reason")
        if data.pop("revision") != 0:
            raise ValidationError("Novo campo exige revisão zero.")
        if CustomFieldDefinition.objects.filter(key=data["key"]).exists():
            raise ValidationError({"key": "Identificador técnico já utilizado."})
        try:
            with transaction.atomic():
                obj = CustomFieldDefinition.objects.create(**data)
        except IntegrityError:
            raise ValidationError({"key": "Identificador técnico já utilizado."})
        record(
            request.user, "custom_field.created", obj, after=FieldOutput(obj).data, reason=reason
        )
        return Response(FieldOutput(obj).data, status=201)

    @extend_schema(request=FieldInput, responses=FieldOutput)
    @transaction.atomic
    def update(self, request, pk=None):
        obj = self.get_queryset().select_for_update().get(pk=self.get_object().pk)
        serializer = FieldInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        reason = data.pop("reason")
        if data.pop("revision") != obj.revision:
            raise ValidationError("Campo alterado. Atualize antes de salvar.")
        if data["key"] != obj.key or data["kind"] != obj.kind:
            raise ValidationError("Identificador e tipo são estáveis. Crie outro campo.")
        before = FieldOutput(obj).data
        for key, value in data.items():
            setattr(obj, key, value)
        obj.revision += 1
        obj.save()
        record(
            request.user,
            "custom_field.updated",
            obj,
            before=before,
            after=FieldOutput(obj).data,
            reason=reason,
        )
        return Response(FieldOutput(obj).data)


class FormView(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = FormOutput
    queryset = FormVersion.objects.select_related("category").all()

    def get_permissions(self):
        return [IsAdministrator()] if self.action == "create" else super().get_permissions()

    @extend_schema(parameters=[OpenApiParameter("category", str), OpenApiParameter("latest", bool)])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset()
        category = self.request.query_params.get("category")
        if category:
            try:
                uuid.UUID(category)
            except ValueError:
                raise ValidationError({"category": "UUID inválido."})
            qs = qs.filter(category_id=category)
        if self.request.query_params.get("latest") == "true":
            latest = (
                FormVersion.objects.filter(category_id=OuterRef("category_id"))
                .order_by("-revision")
                .values("revision")[:1]
            )
            qs = qs.filter(revision=Subquery(latest))
        return qs

    @extend_schema(request=FormInput, responses={201: FormOutput})
    @transaction.atomic
    def create(self, request):
        serializer = FormInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        category = CommitmentCategory.objects.select_for_update().get(pk=data["category"].pk)
        latest = FormVersion.objects.filter(category=category).order_by("revision").last()
        if data["revision"] != (latest.revision if latest else 0):
            raise ValidationError("Formulário alterado. Atualize antes de publicar.")
        fields = list(
            CustomFieldDefinition.objects.select_for_update()
            .filter(pk__in=data["fields"], active=True)
            .order_by("order", "key")
        )
        if len(fields) != len(data["fields"]):
            raise ValidationError({"fields": "Campo indisponível ou inativo."})
        # Fully copied metadata; later field edits cannot change published interpretation.
        obj = FormVersion.objects.create(
            category=category,
            revision=data["revision"] + 1,
            name=data["name"],
            fields=[dict(FieldOutput(f).data) for f in fields],
            actor=request.user,
            reason=data["reason"],
        )
        record(
            request.user,
            "form.published",
            obj,
            before={"revision": data["revision"]},
            after=FormOutput(obj).data,
            reason=data["reason"],
        )
        return Response(FormOutput(obj).data, status=201)


class ReferenceUsers(generics.ListAPIView):
    serializer_class = PersonSerializer

    @extend_schema(parameters=[OpenApiParameter("unit", str, required=True)])
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return User.objects.none()
        unit = self.request.query_params.get("unit", "")
        try:
            uuid.UUID(unit)
        except ValueError:
            raise ValidationError({"unit": "UUID obrigatório."})
        if not OrganizationalUnit.objects.filter(pk=unit, active=True).exists() or not has_role(
            self.request.user, unit, "requester"
        ):
            raise PermissionDenied("Sem permissão na unidade.")
        return (
            User.objects.filter(is_active=True, memberships__unit_id=unit)
            .distinct()
            .order_by("username")
        )
