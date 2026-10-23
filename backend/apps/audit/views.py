from rest_framework import generics, serializers
from apps.accounts.permissions import IsAdministrator
from .models import AuditEvent


class AuditSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.username", read_only=True, default="Sistema")

    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "occurred_at",
            "actor_name",
            "operation",
            "record_type",
            "record_id",
            "unit",
            "before",
            "after",
            "reason",
        ]


class AuditList(generics.ListAPIView):
    permission_classes = [IsAdministrator]
    serializer_class = AuditSerializer

    def get_queryset(self):
        qs = AuditEvent.objects.select_related("actor").all()
        record_id = self.request.query_params.get("record_id")
        return qs.filter(record_id=record_id) if record_id else qs
