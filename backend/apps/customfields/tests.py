from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase
from django.db import DatabaseError, transaction
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.exceptions import ValidationError
from apps.accounts.models import User, Membership
from apps.organizations.models import OrganizationalUnit
from apps.commitments.models import (
    IdentifierCounter,
    RegulatoryEntity,
    CommitmentCategory,
    CommitmentOccurrence,
)
from apps.commitments.services import create_commitment, update_occurrence
from apps.audit.models import AuditEvent
from .models import FormVersion, CustomFieldDefinition
from .serializers import FieldInput
from .validation import validate_value, validate_metadata, validate_values, KINDS


def field(kind="short_text", **overrides):
    return {
        "key": "test",
        "name": "Test",
        "kind": kind,
        "description": "",
        "required": False,
        "default": None,
        "rules": {},
        "options": (
            [{"value": "a", "label": "Alpha"}, {"value": "b", "label": "Beta"}]
            if kind in {"single_select", "multi_select"}
            else []
        ),
        "order": 0,
        "active": True,
        "revision": 0,
        "reason": "Fictitious test",
        **overrides,
    }


class ValueTests(TestCase):
    def test_all_thirteen_types_and_invalid_values(self):
        valid = {
            "short_text": "abc",
            "long_text": "long\ntext",
            "integer": 2,
            "decimal": "123.4500",
            "date": "2028-02-29",
            "datetime": "2026-10-11T14:30:00-03:00",
            "single_select": "a",
            "multi_select": ["a", "b"],
            "boolean": False,
            "url": "https://example.com/a",
            "email": "test@example.com",
        }
        bad = {
            "short_text": 123,
            "long_text": ["a"],
            "integer": True,
            "decimal": 1.2,
            "date": "2027-02-29",
            "datetime": "2026-10-11T12:00:00",
            "single_select": "c",
            "multi_select": ["a", "a"],
            "boolean": "false",
            "url": "javascript:alert(1)",
            "email": "bad",
        }
        self.assertEqual(len(KINDS), 13)
        for kind, value in valid.items():
            with self.subTest(kind=kind):
                self.assertEqual(validate_value(field(kind), value), value)
                with self.assertRaises(ValidationError):
                    validate_value(field(kind), bad[kind])
        for kind in ["user", "unit"]:
            with self.assertRaises(ValidationError):
                validate_value(field(kind), "invalid-uuid")

    def test_invalid_unicode_and_null_characters_rejected_before_storage(self):
        for value in ["bad\x00text", "bad\ud800text"]:
            with self.assertRaises(ValidationError):
                validate_value(field("short_text"), value)
            with self.assertRaises(ValidationError):
                validate_metadata(field("single_select", options=[{"value": "a", "label": value}]))

    def test_numeric_precision_and_bounds(self):
        for value in [9007199254740992, 1.2, "2"]:
            with self.assertRaises(ValidationError):
                validate_value(field("integer"), value)
        for value in ["NaN", "Infinity", "1e4", "1.123456789", "1" * 29, True]:
            with self.assertRaises(ValidationError):
                validate_value(field("decimal"), value)
        for kind, value, rules in [
            ("integer", -1, {"min": 0}),
            ("decimal", "3.11", {"max": "3.10"}),
            ("decimal", "2.123", {"decimal_places": 2}),
        ]:
            with self.assertRaises(ValidationError):
                validate_value(field(kind, rules=rules), value)
        self.assertEqual(validate_value(field("decimal"), "0.00000001"), "0.00000001")

    def test_datetime_compares_instants_and_date_bounds(self):
        f = field("datetime", rules={"min": "2026-10-11T12:00:00Z", "max": "2026-10-11T12:10:00Z"})
        self.assertEqual(
            validate_value(f, "2026-10-11T09:05:00-03:00"), "2026-10-11T09:05:00-03:00"
        )
        with self.assertRaises(ValidationError):
            validate_value(f, "2026-10-11T09:11:00-03:00")
        with self.assertRaises(ValidationError):
            validate_value(field("date", rules={"min": "2026-01-01"}), "2025-12-31")

    def test_required_false_zero_and_empty(self):
        self.assertIs(validate_value(field("boolean", required=True), False), False)
        self.assertEqual(validate_value(field("integer", required=True), 0), 0)
        for value in [None, "", []]:
            with self.assertRaises(ValidationError):
                validate_value(field(required=True), value)
        with self.assertRaises(ValidationError):
            validate_value(field("multi_select"), ["a", 1])

    def test_metadata_rejects_unbounded_or_wrong_rules_and_defaults(self):
        invalid = [
            field(key="Bad-key"),
            field(rules={"regex": "(a+)+$"}),
            field(rules={"max_length": 501}),
            field(rules={"min_length": 5, "max_length": 2}),
            field("decimal", rules={"min": "9", "max": "1"}),
            field("integer", rules={"min": False}),
            field("date", rules={"min": None}),
            field("datetime", rules={"min": "2026-01-01"}),
            field("single_select", options=[]),
            field(
                "single_select",
                options=[{"value": "a", "label": "A"}, {"value": "a", "label": "B"}],
            ),
            field("user", default="00000000-0000-0000-0000-000000000001"),
            field("integer", default="5"),
            field("url", default="file:///secret"),
        ]
        for data in invalid:
            with self.subTest(data=data):
                with self.assertRaises(ValidationError):
                    validate_metadata(data)
        for kind in ["short_text", "decimal", "boolean"]:
            data = field(
                kind, default={"short_text": "ok", "decimal": "1.23", "boolean": False}[kind]
            )
            self.assertEqual(validate_metadata(data), data)
        s = FieldInput(data=field(kind="unknown"))
        self.assertFalse(s.is_valid())


class IntegrationTests(TestCase):
    def setUp(self):
        IdentifierCounter.objects.get_or_create(name="commitment")
        self.admin = User.objects.create_superuser("admin")
        self.owner = User.objects.create_user("owner")
        self.executor = User.objects.create_user("executor")
        self.other = User.objects.create_user("other")
        self.unit = OrganizationalUnit.objects.create(code="a", name="Alpha")
        self.other_unit = OrganizationalUnit.objects.create(code="b", name="Beta")
        Membership.objects.create(user=self.owner, unit=self.unit, role="requester")
        Membership.objects.create(user=self.executor, unit=self.unit, role="executor")
        Membership.objects.create(user=self.other, unit=self.other_unit, role="requester")
        self.category = CommitmentCategory.objects.create(name="Fictitious category")
        self.entity = RegulatoryEntity.objects.create(name="Fictitious entity")
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.data = {
            "title": "Fictitious",
            "description": "Test",
            "legal_basis": "",
            "unit": self.unit,
            "entity": self.entity,
            "category": self.category,
            "assignees": [self.executor],
            "reference_date": timezone.localdate(),
            "due_date": timezone.localdate() + timedelta(days=3),
            "priority": "normal",
        }

    def create_field(self, kind="short_text", **kwargs):
        response = self.client.post("/api/v1/custom-fields/", field(kind, **kwargs), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def publish(self, fields, revision=0):
        response = self.client.post(
            "/api/v1/form-versions/",
            {
                "category": str(self.category.pk),
                "name": "Additional data",
                "fields": [f["id"] for f in fields],
                "revision": revision,
                "reason": "Fictitious publication",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        return FormVersion.objects.get(pk=response.data["id"])

    def test_admin_crud_audit_immutable_keys_and_revision(self):
        f = self.create_field(default="initial")
        for user in [self.owner, self.executor]:
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get("/api/v1/custom-fields/").status_code, 403)
            self.assertEqual(
                self.client.post(
                    "/api/v1/custom-fields/", field(key="other"), format="json"
                ).status_code,
                403,
            )
        self.client.force_authenticate(self.admin)
        body = field(name="Updated", revision=1, default="new")
        response = self.client.put("/api/v1/custom-fields/" + f["id"] + "/", body, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["revision"], 2)
        self.assertEqual(
            self.client.put(
                "/api/v1/custom-fields/" + f["id"] + "/", body, format="json"
            ).status_code,
            400,
        )
        body["revision"] = 2
        body["kind"] = "long_text"
        self.assertEqual(
            self.client.put(
                "/api/v1/custom-fields/" + f["id"] + "/", body, format="json"
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.delete("/api/v1/custom-fields/" + f["id"] + "/").status_code, 405
        )
        self.assertEqual(
            self.client.post("/api/v1/custom-fields/", field(), format="json").status_code, 400
        )
        self.assertEqual(
            AuditEvent.objects.filter(operation__startswith="custom_field.").count(), 2
        )

    def test_publication_defaults_versions_no_silent_change(self):
        f = self.create_field(required=True, default="original")
        form = self.publish([f])
        occurrence = create_commitment(self.owner, {**self.data, "form_version": form.pk})
        self.assertEqual(occurrence.custom_values, {"test": "original"})
        self.assertEqual(occurrence.versions.get().snapshot["form_version"], str(form.pk))
        self.assertEqual(occurrence.definition.custom_values, occurrence.custom_values)
        response = self.client.put(
            "/api/v1/custom-fields/" + f["id"] + "/",
            field(name="New label", default="new default", required=True, revision=1),
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        second = self.publish([f], revision=1)
        form.refresh_from_db()
        self.assertEqual(form.fields[0]["name"], "Test")
        self.assertEqual(form.fields[0]["default"], "original")
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.form_version, form)
        with self.assertRaises(ValidationError):
            create_commitment(self.owner, {**self.data, "form_version": form.pk})
        new = create_commitment(self.owner, {**self.data, "form_version": second.pk})
        self.assertEqual(new.custom_values, {"test": "new default"})
        self.client.force_authenticate(self.executor)
        detail = self.client.get("/api/v1/occurrences/" + str(occurrence.pk) + "/")
        self.assertEqual(detail.data["form_schema"]["fields"][0]["name"], "Test")
        self.client.force_authenticate(self.other)
        self.assertEqual(
            self.client.get("/api/v1/occurrences/" + str(occurrence.pk) + "/").status_code, 404
        )

    def test_edit_complete_values_required_and_audited_snapshots(self):
        form = self.publish([self.create_field(required=True)])
        for values in [{}, {"test": ""}, {"test": "a", "injected": "x"}]:
            with self.assertRaises(ValidationError):
                create_commitment(
                    self.owner, {**self.data, "form_version": form.pk, "custom_values": values}
                )
        occurrence = create_commitment(
            self.owner, {**self.data, "form_version": form.pk, "custom_values": {"test": "a"}}
        )
        before = deepcopy(occurrence.versions.get().snapshot)
        occurrence = update_occurrence(
            self.owner,
            occurrence,
            {"custom_values": {"test": "b"}, "reason": "Corrected", "revision": 1},
        )
        self.assertEqual(occurrence.custom_values, {"test": "b"})
        self.assertEqual(occurrence.versions.get(revision=1).snapshot, before)
        self.assertEqual(
            AuditEvent.objects.get(operation="occurrence.updated").before["custom_values"],
            {"test": "a"},
        )
        with self.assertRaises(ValidationError):
            update_occurrence(
                self.owner, occurrence, {"custom_values": {}, "reason": "Bad", "revision": 2}
            )
        self.client.force_authenticate(self.owner)
        self.assertEqual(
            self.client.patch(
                "/api/v1/occurrences/" + str(occurrence.pk) + "/edit/",
                {"form_version": None, "reason": "Bad", "revision": 2},
                format="json",
            ).status_code,
            400,
        )
        occurrence.status = "completed"
        occurrence.save()
        with self.assertRaises(ValidationError):
            update_occurrence(
                self.owner,
                occurrence,
                {"custom_values": {"test": "c"}, "reason": "Bad", "revision": 2},
            )

    def test_reference_scope_and_historical_inactive_value(self):
        for kind, valid, invalid in [
            ("user", str(self.executor.pk), str(self.other.pk)),
            ("unit", str(self.unit.pk), str(self.other_unit.pk)),
        ]:
            self.assertEqual(validate_value(field(kind), valid, self.unit), valid)
            with self.assertRaises(ValidationError):
                validate_value(field(kind), invalid, self.unit)
        self.client.force_authenticate(self.owner)
        users = self.client.get("/api/v1/custom-field-users/?unit=" + str(self.unit.pk))
        self.assertEqual(users.status_code, 200)
        self.assertEqual({r["username"] for r in users.data["results"]}, {"owner", "executor"})
        self.assertEqual(
            self.client.get(
                "/api/v1/custom-field-users/?unit=" + str(self.other_unit.pk)
            ).status_code,
            403,
        )
        self.assertEqual(self.client.get("/api/v1/custom-field-users/?unit=oops").status_code, 400)
        self.client.force_authenticate(self.admin)
        form = self.publish([self.create_field("user")])
        occurrence = create_commitment(
            self.owner,
            {
                **self.data,
                "form_version": form.pk,
                "custom_values": {"test": str(self.executor.pk)},
            },
        )
        self.executor.is_active = False
        self.executor.save()
        updated = update_occurrence(
            self.owner,
            occurrence,
            {"custom_values": occurrence.custom_values, "revision": 1, "reason": "Keep historical"},
        )
        self.assertEqual(updated.custom_values, occurrence.custom_values)
        with self.assertRaises(ValidationError):
            validate_value(field("user"), str(self.executor.pk), self.unit)

    def test_form_is_append_only_and_publication_atomic(self):
        f = self.create_field()
        form = self.publish([f])
        for action in [
            lambda: FormVersion.objects.filter(pk=form.pk).update(name="Bad"),
            lambda: form.delete(),
        ]:
            with self.assertRaises(DatabaseError), transaction.atomic():
                action()
        with patch("apps.customfields.views.record", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                self.publish([f], 1)
        self.assertEqual(FormVersion.objects.count(), 1)
        payload = {
            "category": str(self.category.pk),
            "name": "Test",
            "fields": [f["id"]],
            "revision": 0,
            "reason": "Bad",
        }
        self.assertEqual(
            self.client.post("/api/v1/form-versions/", payload, format="json").status_code, 400
        )
        payload["revision"] = 1
        payload["fields"] = [f["id"], f["id"]]
        self.assertEqual(
            self.client.post("/api/v1/form-versions/", payload, format="json").status_code, 400
        )
        CustomFieldDefinition.objects.filter(pk=f["id"]).update(active=False)
        payload["fields"] = [f["id"]]
        self.assertEqual(
            self.client.post("/api/v1/form-versions/", payload, format="json").status_code, 400
        )

    def test_empty_form_and_legacy_occurrences(self):
        old = create_commitment(self.owner, self.data)
        form = self.publish([self.create_field()])
        with self.assertRaises(ValidationError):
            create_commitment(self.owner, self.data)
        empty = self.publish([], 1)
        new = create_commitment(self.owner, {**self.data, "form_version": empty.pk})
        self.assertEqual(new.custom_values, {})
        old.refresh_from_db()
        self.assertIsNone(old.form_version)
        self.assertEqual(old.custom_values, {})
        with self.assertRaises(ValidationError):
            validate_values(form, {"x": 1}, self.unit)
        self.client.force_authenticate(self.owner)
        response = self.client.get(
            "/api/v1/form-versions/?category=" + str(self.category.pk) + "&latest=true"
        )
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], str(empty.pk))
        self.assertEqual(self.client.get("/api/v1/form-versions/?category=bad").status_code, 400)
        self.assertEqual(
            self.client.post("/api/v1/form-versions/", {}, format="json").status_code, 403
        )

    def test_recurrence_freezes_form_and_values(self):
        form = self.publish([self.create_field("decimal", default="1.20")])
        start = self.data["due_date"]
        rule = {
            "frequency": "monthly",
            "start": start.isoformat(),
            "end": (start + timedelta(days=80)).isoformat(),
            "interval": 1,
            "count": 3,
            "month_mode": "day",
            "month_day": start.day,
            "weekday": 0,
            "adjustment": "none",
            "calendar": "institution",
            "exceptions": [],
        }
        from apps.commitments.recurrence_serializers import RuleSerializer

        serializer = RuleSerializer(data=rule)
        serializer.is_valid(raise_exception=True)
        first = create_commitment(
            self.owner,
            {**self.data, "form_version": form.pk, "recurrence": serializer.validated_data},
        )
        self.assertGreater(first.definition.occurrences.count(), 1)
        self.publish([], 1)
        for occurrence in first.definition.occurrences.all():
            self.assertEqual(occurrence.form_version, form)
            self.assertEqual(occurrence.custom_values, {"test": "1.20"})
        update_occurrence(
            self.owner,
            first,
            {"custom_values": {"test": "2.30"}, "revision": 1, "reason": "Occurrence only"},
        )
        self.assertTrue(
            first.definition.occurrences.exclude(pk=first.pk)
            .filter(custom_values={"test": "1.20"})
            .exists()
        )
        self.assertEqual(
            CommitmentOccurrence.objects.filter(definition=first.definition).count(), 3
        )
