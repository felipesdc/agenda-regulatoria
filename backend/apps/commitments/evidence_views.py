import hashlib
import hmac
from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.http import content_disposition_header
from django.utils.module_loading import import_string
from rest_framework import generics, serializers
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiTypes
from apps.audit.services import record
from .views import scoped_occurrences
from .models import Evidence
from .serializers import EvidenceSerializer, StrictSerializer
from .evidence import EvidenceUnavailable, FORMATS, withdraw


class PrivateEvidence(generics.GenericAPIView):
    serializer_class = EvidenceSerializer

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store, private"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    def evidence(self):
        return get_object_or_404(
            Evidence.objects.filter(
                action__occurrence__in=scoped_occurrences(self.request.user)
            ).select_related(
                "action__occurrence__definition__unit",
                "action__occurrence__definition__requester",
                "withdrawal",
            ),
            pk=self.kwargs["pk"],
        )


class EvidenceDownload(PrivateEvidence):
    @extend_schema(responses={(200, "application/octet-stream"): OpenApiTypes.BINARY})
    @transaction.atomic
    def get(self, request, pk):
        evidence = self.evidence()
        if hasattr(evidence, "withdrawal"):
            return Response(
                {"detail": "Evidência retirada; o histórico foi preservado."}, status=410
            )
        if not settings.DEBUG and evidence.inspection != "clamd:OK":
            raise EvidenceUnavailable()
        try:
            with import_string(evidence.storage_backend)().open(evidence.storage_key, "rb") as file:
                data = file.read(evidence.size + 1)
        except Exception as exc:
            raise EvidenceUnavailable() from exc
        if len(data) != evidence.size or not hmac.compare_digest(
            hashlib.sha256(data).hexdigest(), evidence.sha256
        ):
            raise EvidenceUnavailable()
        record(
            request.user,
            "evidence.downloaded",
            evidence,
            evidence.action.occurrence.definition.unit,
            after={
                "sha256": evidence.sha256,
                "size": evidence.size,
                "occurrence": str(evidence.action.occurrence_id),
            },
        )
        return HttpResponse(
            data,
            content_type="application/octet-stream",
            headers={"Content-Disposition": content_disposition_header(True, evidence.filename)},
        )


class WithdrawalInput(StrictSerializer):
    reason = serializers.CharField(max_length=1000)


class EvidenceWithdraw(PrivateEvidence):
    @extend_schema(request=WithdrawalInput, responses=EvidenceSerializer)
    def post(self, request, pk):
        evidence = self.evidence()
        serializer = WithdrawalInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        withdraw(request.user, evidence, serializer.validated_data["reason"])
        evidence = self.evidence()
        return Response(EvidenceSerializer(evidence, context={"request": request}).data)


class EvidencePolicyOutput(serializers.Serializer):
    max_file_bytes = serializers.IntegerField()
    max_files = serializers.IntegerField()
    max_total_bytes = serializers.IntegerField()
    extensions = serializers.ListField(child=serializers.CharField())
    antivirus_required = serializers.BooleanField()
    scanner_configured = serializers.BooleanField()


class EvidencePolicy(PrivateEvidence):
    serializer_class = EvidencePolicyOutput

    def get(self, request):
        return Response(
            {
                "max_file_bytes": settings.EVIDENCE_MAX_FILE_BYTES,
                "max_files": settings.EVIDENCE_MAX_FILES,
                "max_total_bytes": 10 * 1024 * 1024,
                "extensions": list(FORMATS),
                "antivirus_required": not settings.DEBUG,
                "scanner_configured": bool(settings.EVIDENCE_SCANNER_HOST),
            }
        )
