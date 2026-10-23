from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase, TransactionTestCase
from django.db import transaction, IntegrityError, DatabaseError, connection
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.exceptions import ValidationError, PermissionDenied
from apps.accounts.models import User, Membership
from apps.organizations.models import OrganizationalUnit
from apps.audit.models import AuditEvent
from .models import (
    RegulatoryEntity,
    CommitmentCategory,
    CommitmentDefinition,
    IdentifierCounter,
    CommitmentAssignment,
    ActionRecord,
    WorkflowTransition,
)
from . import services


class CommitmentTests(TestCase):
    def setUp(self):
        # TransactionTestCase flush removes migration seed rows between tests.
        IdentifierCounter.objects.get_or_create(name="commitment")
        self.unit = OrganizationalUnit.objects.create(code="A", name="Alpha")
        self.other = OrganizationalUnit.objects.create(code="B", name="Beta")
        self.requester = User.objects.create_user("requester")
        self.executor = User.objects.create_user("executor")
        self.stranger = User.objects.create_user("stranger")
        self.peer = User.objects.create_user("peer")
        self.admin = User.objects.create_superuser("global")
        Membership.objects.create(user=self.requester, unit=self.unit, role="requester")
        Membership.objects.create(user=self.peer, unit=self.unit, role="requester")
        Membership.objects.create(user=self.executor, unit=self.unit, role="executor")
        Membership.objects.create(user=self.stranger, unit=self.other, role="requester")
        self.entity = RegulatoryEntity.objects.create(name="Fictitious entity")
        self.category = CommitmentCategory.objects.create(name="Fictitious category")
        self.data = {
            "title": "Fictitious obligation",
            "description": "Test only",
            "legal_basis": "",
            "unit": self.unit,
            "entity": self.entity,
            "category": self.category,
            "assignees": [self.executor],
            "reference_date": timezone.localdate(),
            "due_date": timezone.localdate() + timedelta(days=3),
            "priority": "normal",
        }
        self.occ = services.create_commitment(self.requester, self.data)
        self.client = APIClient()

    def move(self, user, op, reason=""):
        self.occ.refresh_from_db()
        self.occ = services.transition(user, self.occ, op, reason, self.occ.revision)
        return self.occ

    def payload(self):
        return {
            **{
                k: v
                for k, v in self.data.items()
                if k
                not in ["unit", "entity", "category", "assignees", "reference_date", "due_date"]
            },
            "unit": str(self.unit.pk),
            "entity": str(self.entity.pk),
            "category": str(self.category.pk),
            "assignees": [str(self.executor.pk)],
            "reference_date": str(self.data["reference_date"]),
            "due_date": str(self.data["due_date"]),
        }

    def test_creation_unique_identifiers_snapshots(self):
        second = services.create_commitment(self.requester, self.data)
        self.assertNotEqual(second.identifier, self.occ.identifier)
        self.assertRegex(self.occ.definition.identifier, r"^REG-\d{6}$")
        self.assertTrue(self.occ.identifier.endswith("/0001"))
        self.assertEqual(self.occ.versions.get().snapshot["assignees"], [str(self.executor.pk)])
        with self.assertRaises(IntegrityError), transaction.atomic():
            CommitmentAssignment.objects.create(occurrence=self.occ, user=self.executor)

    def test_creation_scope_and_assignments(self):
        for user in [self.executor, self.stranger]:
            with self.assertRaises(PermissionDenied):
                services.create_commitment(user, self.data)
        for users in [[], [self.executor, self.executor], [self.stranger], [self.admin]]:
            with self.assertRaises(ValidationError):
                services.create_commitment(self.requester, {**self.data, "assignees": users})
        self.executor.is_active = False
        self.executor.save()
        with self.assertRaises(ValidationError):
            services.create_commitment(self.requester, self.data)
        self.unit.active = False
        self.unit.save()
        with self.assertRaises(PermissionDenied):
            services.create_commitment(self.admin, self.data)

    def test_atomic_creation_on_audit_failure(self):
        before = IdentifierCounter.objects.get(name="commitment").value
        with (
            patch("apps.commitments.services.record", side_effect=RuntimeError()),
            self.assertRaises(RuntimeError),
        ):
            services.create_commitment(self.requester, self.data)
        self.assertEqual(CommitmentDefinition.objects.count(), 1)
        self.assertEqual(IdentifierCounter.objects.get(name="commitment").value, before)

    def test_success_workflow_and_independent_occurrences(self):
        second = services.create_commitment(self.requester, self.data)
        self.move(self.executor, "start")
        services.add_action(self.executor, self.occ, "Completed verification")
        self.move(self.executor, "submit")
        self.assertEqual(self.occ.status, "awaiting_validation")
        self.move(self.requester, "approve")
        self.assertEqual(self.occ.status, "completed")
        self.assertIsNotNone(self.occ.completed_at)
        self.assertEqual(self.occ.transitions.count(), 3)
        self.assertTrue(AuditEvent.objects.filter(operation="workflow.approve").exists())
        second.refresh_from_db()
        self.assertEqual(second.status, "pending")

    def test_rejection_requires_new_providence(self):
        self.move(self.executor, "start")
        services.add_action(self.executor, self.occ, "Initial work")
        self.move(self.executor, "submit")
        with self.assertRaises(ValidationError):
            self.move(self.requester, "reject")
        self.move(self.requester, "reject", "Complement required")
        self.move(self.executor, "start")
        with self.assertRaises(ValidationError):
            self.move(self.executor, "submit")
        services.add_action(self.executor, self.occ, "Complement completed")
        self.move(self.executor, "submit")
        self.move(self.requester, "approve")
        self.assertEqual(self.occ.status, "completed")

    def test_transition_guards(self):
        for actor, operation in [
            (self.requester, "start"),
            (self.executor, "approve"),
            (self.executor, "submit"),
            (self.peer, "cancel"),
        ]:
            with self.assertRaises(PermissionDenied):
                self.move(actor, operation)
        self.move(self.executor, "start")
        with self.assertRaises(ValidationError):
            self.move(self.executor, "submit")
        with self.assertRaises(ValidationError):
            services.transition(self.executor, self.occ, "submit", "", 1)
        with self.assertRaises(PermissionDenied):
            services.add_action(self.requester, self.occ, "No")

    def test_self_approval_even_administrator(self):
        Membership.objects.create(user=self.requester, unit=self.unit, role="executor")
        self.occ.assignments.all().delete()
        CommitmentAssignment.objects.create(user=self.requester, occurrence=self.occ)
        self.move(self.requester, "start")
        services.add_action(self.requester, self.occ, "Self work")
        self.move(self.requester, "submit")
        with self.assertRaises(PermissionDenied):
            self.move(self.requester, "approve")
        self.requester.is_superuser = True
        self.requester.save()
        with self.assertRaises(PermissionDenied):
            self.move(self.requester, "approve")
        self.move(self.admin, "approve")

    def test_cancel_reopen_and_frozen_history(self):
        with self.assertRaises(ValidationError):
            self.move(self.requester, "cancel")
        self.move(self.requester, "cancel", "No longer needed")
        with self.assertRaises(PermissionDenied):
            self.move(self.executor, "start")
        with self.assertRaises(ValidationError):
            services.update_occurrence(
                self.requester,
                self.occ,
                {"title": "No", "revision": self.occ.revision, "reason": "No"},
            )
        self.occ = services.create_commitment(self.requester, self.data)
        self.move(self.executor, "start")
        services.add_action(self.executor, self.occ, "Work")
        self.move(self.executor, "submit")
        self.move(self.requester, "approve")
        with self.assertRaises(ValidationError):
            self.move(self.requester, "reopen")
        self.move(self.requester, "reopen", "Explicit correction")
        self.assertIsNone(self.occ.completed_at)
        self.assertIsNone(self.occ.submitted_by_id)
        self.assertEqual(self.occ.actions.count(), 1)
        self.assertEqual(self.occ.transitions.count(), 4)

    def test_update_snapshot_reassignment_and_conflict(self):
        old = self.occ.versions.get().snapshot
        second = User.objects.create_user("second")
        Membership.objects.create(user=second, unit=self.unit, role="executor")
        self.occ = services.update_occurrence(
            self.requester,
            self.occ,
            {
                "title": "Updated",
                "revision": 1,
                "reason": "Change",
                "assignees": [second],
                "due_date": timezone.localdate() + timedelta(days=10),
            },
        )
        self.assertEqual(self.occ.title, "Updated")
        self.assertEqual(self.occ.definition.title, "Fictitious obligation")
        self.assertEqual(self.occ.versions.count(), 2)
        self.assertEqual(self.occ.versions.get(revision=1).snapshot, old)
        self.assertFalse(services.can_execute(self.executor, self.occ))
        with self.assertRaises(ValidationError):
            services.update_occurrence(
                self.requester,
                self.occ,
                {"title": "Overwrite", "revision": 1, "reason": "Conflict"},
            )
        with self.assertRaises(PermissionDenied):
            services.update_occurrence(
                self.peer, self.occ, {"title": "No", "revision": 2, "reason": "No"}
            )

    def test_derived_overdue(self):
        self.occ.due_date = timezone.localdate() - timedelta(days=1)
        self.assertTrue(self.occ.overdue)
        for status in ["completed", "cancelled"]:
            self.occ.status = status
            self.assertFalse(self.occ.overdue)

    def test_database_history_append_only(self):
        event = AuditEvent.objects.first()
        with self.assertRaises(ValueError):
            event.save()
        with self.assertRaises(ValueError):
            event.delete()
        with self.assertRaises(DatabaseError), transaction.atomic():
            AuditEvent.objects.filter(pk=event.pk).update(reason="Silenced")
        with self.assertRaises(DatabaseError), transaction.atomic():
            self.occ.versions.all().delete()
        self.move(self.executor, "start")
        services.add_action(self.executor, self.occ, "Immutable")
        for model in [ActionRecord, WorkflowTransition]:
            with self.assertRaises(DatabaseError), transaction.atomic():
                model.objects.all().delete()

    def test_api_scope_security_and_roles(self):
        url = f"/api/v1/occurrences/{self.occ.pk}/"
        self.assertEqual(self.client.get(url).status_code, 403)
        for user, count, status in [
            (self.stranger, 0, 404),
            (self.executor, 1, 200),
            (self.requester, 1, 200),
            (self.admin, 1, 200),
        ]:
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get("/api/v1/occurrences/").data["count"], count)
            self.assertEqual(self.client.get(url).status_code, status)
        unassigned = User.objects.create_user("unassigned")
        Membership.objects.create(user=unassigned, unit=self.unit, role="executor")
        self.client.force_authenticate(unassigned)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_authenticate(self.executor)
        self.assertEqual(self.client.get("/api/v1/audit/").status_code, 403)
        self.assertEqual(
            self.client.get("/api/v1/assignable-users/", {"unit": str(self.unit.pk)}).status_code,
            403,
        )
        self.assertEqual(self.client.post("/api/v1/entities/", {"name": "No"}).status_code, 403)
        self.assertEqual(
            self.client.post("/api/v1/definitions/", self.payload(), format="json").status_code, 403
        )
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get("/api/v1/audit/").status_code, 200)
        self.assertEqual(self.client.post("/api/v1/entities/", {"name": "New"}).status_code, 201)
        self.assertEqual(self.client.post("/api/v1/categories/", {"name": "New"}).status_code, 201)

    def test_api_create_edit_validation_and_filters(self):
        self.client.force_authenticate(self.requester)
        response = self.client.post("/api/v1/definitions/", self.payload(), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        url = f"/api/v1/occurrences/{self.occ.pk}"
        self.assertEqual(self.client.patch(url + "/", {"status": "completed"}).status_code, 405)
        self.assertEqual(
            self.client.patch(
                url + "/edit/",
                {"status": "completed", "revision": 1, "reason": "Bypass"},
                format="json",
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.patch(
                url + "/edit/",
                {"title": "Edited", "revision": 1, "reason": "Correction"},
                format="json",
            ).status_code,
            200,
        )
        self.assertEqual(self.client.get("/api/v1/definitions/").data["count"], 2)
        definition = str(self.occ.definition_id)
        self.assertEqual(self.client.get(f"/api/v1/definitions/{definition}/").status_code, 200)
        self.assertEqual(
            self.client.get(
                "/api/v1/occurrences/",
                {
                    "q": "Edited",
                    "status": "pending",
                    "unit": str(self.unit.pk),
                    "entity": str(self.entity.pk),
                    "category": str(self.category.pk),
                },
            ).data["count"],
            1,
        )
        for query in [
            {"status": "invalid"},
            {"unit": "bad"},
            {"entity": "bad"},
            {"category": "bad"},
        ]:
            self.assertEqual(self.client.get("/api/v1/occurrences/", query).status_code, 400)
        self.assertEqual(
            self.client.get("/api/v1/assignable-users/", {"unit": "bad"}).status_code, 400
        )
        self.assertEqual(
            self.client.get("/api/v1/assignable-users/", {"unit": str(self.unit.pk)}).data["count"],
            1,
        )
        self.assertEqual(
            self.client.get("/api/v1/occurrences/", {"validation": "true", "overdue": "true"}).data[
                "count"
            ],
            0,
        )
        self.client.force_authenticate(self.executor)
        self.assertEqual(self.client.get("/api/v1/occurrences/", {"mine": "true"}).data["count"], 2)

    def test_api_execution_actions(self):
        self.client.force_authenticate(self.executor)
        url = f"/api/v1/occurrences/{self.occ.pk}"
        self.assertEqual(self.client.post(url + "/actions/", {"text": "Too soon"}).status_code, 400)
        self.assertEqual(
            self.client.post(
                url + "/transition/", {"operation": "start", "revision": 1}, format="json"
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(url + "/actions/", {"text": "Performed"}, format="json").status_code,
            201,
        )
        self.assertEqual(
            self.client.post(
                url + "/transition/", {"operation": "submit", "revision": 2}, format="json"
            ).status_code,
            200,
        )
        self.client.force_authenticate(self.requester)
        self.assertEqual(
            self.client.get("/api/v1/occurrences/", {"validation": "true"}).data["count"], 1
        )
        self.assertEqual(
            self.client.post(
                url + "/transition/", {"operation": "approve", "revision": 3}, format="json"
            ).status_code,
            200,
        )
        self.client.force_authenticate(self.admin)
        self.assertGreater(
            self.client.get("/api/v1/audit/", {"record_id": str(self.occ.pk)}).data["count"], 0
        )

    def test_scope_revocation(self):
        self.client.force_authenticate(self.executor)
        self.unit.active = False
        self.unit.save()
        self.assertEqual(self.client.get("/api/v1/occurrences/").data["count"], 0)
        self.assertFalse(services.can_execute(self.executor, self.occ))

    def test_admin_membership_provisioning_audited(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            "/admin/accounts/membership/add/",
            {
                "user": str(self.executor.pk),
                "unit": str(self.other.pk),
                "role": "executor",
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 302)
        membership = Membership.objects.get(user=self.executor, unit=self.other, role="executor")
        self.assertTrue(
            AuditEvent.objects.filter(
                operation="membership.created", record_id=str(membership.pk), actor=self.admin
            ).exists()
        )
        self.peer.is_staff = True
        self.peer.save()
        from django.contrib.auth.models import Permission

        self.peer.user_permissions.add(Permission.objects.get(codename="add_membership"))
        self.client.force_login(self.peer)
        self.assertEqual(self.client.get("/admin/accounts/membership/add/").status_code, 403)

    def test_unit_cycle_validation_and_audited_admin_change(self):
        from django.core.exceptions import ValidationError as DjangoValidationError

        self.other.parent = self.unit
        self.other.save()
        self.unit.parent = self.other
        with self.assertRaises(DjangoValidationError):
            self.unit.full_clean()
        self.unit.parent = None
        self.client.force_login(self.admin)
        response = self.client.post(
            f"/admin/organizations/organizationalunit/{self.unit.pk}/change/",
            {"name": "Renamed Alpha", "code": "A", "parent": "", "active": "on", "_save": "Save"},
        )
        self.assertEqual(response.status_code, 302)
        event = AuditEvent.objects.get(operation="unit.updated", record_id=str(self.unit.pk))
        self.assertEqual(event.before["name"], "Alpha")
        self.assertEqual(event.after["name"], "Renamed Alpha")


class ConcurrentIdentifierTests(TransactionTestCase):
    def test_postgres_concurrent_ids(self):
        if connection.vendor != "postgresql":
            self.skipTest("Row-lock concurrency requires PostgreSQL")
        from concurrent.futures import ThreadPoolExecutor
        from django.db import close_old_connections, connections

        IdentifierCounter.objects.get_or_create(name="commitment")
        unit = OrganizationalUnit.objects.create(code="CONC", name="Concurrent")
        requester = User.objects.create_user("requester")
        executor = User.objects.create_user("executor")
        Membership.objects.create(user=requester, unit=unit, role="requester")
        Membership.objects.create(user=executor, unit=unit, role="executor")
        entity = RegulatoryEntity.objects.create(name="Concurrent")
        category = CommitmentCategory.objects.create(name="Concurrent")
        data = {
            "title": "Concurrent fictitious",
            "description": "Test",
            "legal_basis": "",
            "unit": unit,
            "entity": entity,
            "category": category,
            "assignees": [executor],
            "reference_date": timezone.localdate(),
            "due_date": timezone.localdate(),
            "priority": "normal",
        }

        def create(_):
            close_old_connections()
            try:
                return services.create_commitment(requester, data).identifier
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=4) as pool:
            identifiers = list(pool.map(create, range(8)))
        self.assertEqual(len(set(identifiers)), 8)
