from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.db import transaction
from apps.audit.services import record
from .models import User, Membership


class GlobalAdministratorOnly:
    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)


@admin.register(User)
class AuditedUserAdmin(GlobalAdministratorOnly, UserAdmin):
    @transaction.atomic
    def user_change_password(self, request, id, form_url=""):
        response = super().user_change_password(request, id, form_url)
        if request.method == "POST" and response.status_code == 302:
            record(request.user, "user.password_changed", User.objects.get(pk=id))
        return response

    def save_model(self, request, obj, form, change):
        before = {}
        if change:
            old = User.objects.get(pk=obj.pk)
            before = {
                key: getattr(old, key)
                for key in ["username", "email", "is_active", "is_staff", "is_superuser"]
            }
        super().save_model(request, obj, form, change)
        record(
            request.user,
            "user.updated" if change else "user.created",
            obj,
            before=before,
            after={
                key: getattr(obj, key)
                for key in ["username", "email", "is_active", "is_staff", "is_superuser"]
            },
        )

    def save_related(self, request, form, formsets, change):
        before = {
            "groups": list(form.instance.groups.values_list("name", flat=True)),
            "permissions": list(form.instance.user_permissions.values_list("codename", flat=True)),
        }
        super().save_related(request, form, formsets, change)
        after = {
            "groups": list(form.instance.groups.values_list("name", flat=True)),
            "permissions": list(form.instance.user_permissions.values_list("codename", flat=True)),
        }
        if before != after:
            record(
                request.user, "user.permissions_changed", form.instance, before=before, after=after
            )

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Membership)
class MembershipAdmin(GlobalAdministratorOnly, admin.ModelAdmin):
    list_display = ["user", "unit", "role"]

    def save_model(self, request, obj, form, change):
        before = {}
        if change:
            old = Membership.objects.get(pk=obj.pk)
            before = {"user": str(old.user_id), "unit": str(old.unit_id), "role": old.role}
        super().save_model(request, obj, form, change)
        record(
            request.user,
            "membership.updated" if change else "membership.created",
            obj,
            obj.unit,
            before=before,
            after={"user": str(obj.user_id), "unit": str(obj.unit_id), "role": obj.role},
        )

    def has_delete_permission(self, request, obj=None):
        return False
