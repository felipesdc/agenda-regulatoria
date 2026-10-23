from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, generics
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .permissions import visible_units, IsAdministrator
from .models import User
from apps.organizations.models import OrganizationalUnit
import json


@require_GET
@ensure_csrf_cookie
def csrf(request):
    return JsonResponse({"detail": "CSRF cookie initialized"})


@require_POST
@csrf_protect
def sign_in(request):
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValueError()
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"detail": "Requisição inválida."}, status=400)
    username, password = data.get("username"), data.get("password")
    if (
        not isinstance(username, str)
        or not isinstance(password, str)
        or len(username) > 150
        or len(password) > 4096
    ):
        return JsonResponse({"detail": "Credenciais inválidas."}, status=400)
    user = authenticate(request, username=username, password=password)
    if user is None:
        return JsonResponse(
            {"detail": "Não foi possível autenticar com as credenciais informadas."}, status=401
        )
    login(request, user)
    return JsonResponse({"detail": "Autenticado."})


@extend_schema(
    request=None,
    responses=inline_serializer(name="LogoutResponse", fields={"detail": serializers.CharField()}),
)
@api_view(["POST"])
def sign_out(request):
    logout(request)
    return Response({"detail": "Sessão encerrada."})


@extend_schema(
    responses=inline_serializer(
        name="Profile",
        fields={
            "id": serializers.UUIDField(),
            "username": serializers.CharField(),
            "name": serializers.CharField(),
            "administrator": serializers.BooleanField(),
            "environment": serializers.ChoiceField(choices=["development", "intranet"]),
            "memberships": serializers.ListField(child=serializers.DictField()),
        },
    )
)
@api_view(["GET"])
def me(request):
    user = request.user
    return Response(
        {
            "id": str(user.pk),
            "username": user.username,
            "name": user.get_full_name() or user.username,
            "administrator": user.is_superuser,
            "environment": "development" if settings.DEBUG else "intranet",
            "memberships": list(
                user.memberships.filter(unit__active=True).values("unit_id", "unit__name", "role")
            ),
        }
    )


class UnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganizationalUnit
        fields = ["id", "code", "name", "parent"]


class UnitList(generics.ListAPIView):
    serializer_class = UnitSerializer

    def get_queryset(self):
        return visible_units(self.request.user)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "is_active"]


class UserList(generics.ListAPIView):
    permission_classes = [IsAdministrator]
    serializer_class = UserSerializer
    queryset = User.objects.order_by("username")


@require_GET
def health(request):
    return JsonResponse({"status": "ok"})


@require_GET
def ready(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        if executor.migration_plan(executor.loader.graph.leaf_nodes()):
            return JsonResponse({"status": "unavailable"}, status=503)
        return JsonResponse({"status": "ready"})
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)
