from django.contrib import admin
from apps.accounts.admin import GlobalAdministratorOnly
from apps.audit.services import record
from .models import OrganizationalUnit


@admin.register(OrganizationalUnit)
class OrganizationalUnitAdmin(GlobalAdministratorOnly, admin.ModelAdmin):
    list_display = ["code", "name", "parent", "active"]

    def save_model(self, request, obj, form, change):
        def snapshot(unit):
            return {
                "code": unit.code,
                "name": unit.name,
                "parent": str(unit.parent_id) if unit.parent_id else None,
                "active": unit.active,
            }

        before = snapshot(OrganizationalUnit.objects.get(pk=obj.pk)) if change else {}
        super().save_model(request, obj, form, change)
        record(
            request.user,
            "unit.updated" if change else "unit.created",
            obj,
            obj,
            before=before,
            after=snapshot(obj),
        )

    def has_delete_permission(self, request, obj=None):
        return False
