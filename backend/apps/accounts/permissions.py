from rest_framework.permissions import BasePermission
from .models import Membership


def has_role(user, unit_id, role):
    return (
        user.is_authenticated
        and user.is_active
        and (
            user.is_superuser
            or Membership.objects.filter(
                user=user, unit_id=unit_id, role=role, unit__active=True
            ).exists()
        )
    )


def visible_units(user):
    from apps.organizations.models import OrganizationalUnit

    if not user.is_authenticated or not user.is_active:
        return OrganizationalUnit.objects.none()
    units = OrganizationalUnit.objects.filter(active=True)
    return units if user.is_superuser else units.filter(memberships__user=user).distinct()


class IsAdministrator(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and request.user.is_active and request.user.is_superuser
        )
