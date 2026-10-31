import csv
import io
import json
from datetime import timedelta, datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from apps.accounts.models import User, Membership
from apps.organizations.models import OrganizationalUnit
from apps.commitments.models import (
    IdentifierCounter,
    RegulatoryEntity,
    CommitmentCategory,
    WorkflowTransition,
)
from apps.commitments.services import create_commitment
from apps.audit.models import AuditEvent
from .models import ReportFavorite
from .exports import xlsx_bytes, csv_bytes, column
from rest_framework.exceptions import ValidationError


class ReportTests(TestCase):
    def setUp(self):
        IdentifierCounter.objects.get_or_create(name="commitment")
        self.owner = User.objects.create_user("owner")
        self.executor = User.objects.create_user("executor")
        self.second = User.objects.create_user("second")
        self.stranger = User.objects.create_user("stranger")
        self.admin = User.objects.create_superuser("global")
        self.unit = OrganizationalUnit.objects.create(code="a", name="Alpha")
        self.other = OrganizationalUnit.objects.create(code="b", name="Beta")
        for user, unit, role in [
            (self.owner, self.unit, "requester"),
            (self.executor, self.unit, "executor"),
            (self.second, self.unit, "executor"),
            (self.stranger, self.other, "requester"),
        ]:
            Membership.objects.create(user=user, unit=unit, role=role)
        self.category = CommitmentCategory.objects.create(name="Test category")
        self.entity = RegulatoryEntity.objects.create(name="Test entity")
        self.today = timezone.localdate()
        self.data = {
            "title": "Fictitious report",
            "description": "Test only",
            "legal_basis": "",
            "unit": self.unit,
            "entity": self.entity,
            "category": self.category,
            "assignees": [self.executor, self.second],
            "reference_date": self.today,
            "due_date": self.today,
            "priority": "normal",
        }
        self.pending = create_commitment(self.owner, self.data)
        self.late = create_commitment(
            self.owner, {**self.data, "due_date": self.today - timedelta(days=1)}
        )
        self.done = create_commitment(self.owner, self.data)
        self.done.status = "completed"
        self.done.completed_at = timezone.now()
        self.done.save()
        self.cancelled = create_commitment(self.owner, self.data)
        self.cancelled.status = "cancelled"
        self.cancelled.save()
        Membership.objects.create(user=self.stranger, unit=self.other, role="executor")
        self.hidden = create_commitment(
            self.stranger,
            {**self.data, "unit": self.other, "assignees": [self.stranger], "title": "Secret Beta"},
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.params = {
            "date_start": str(self.today - timedelta(days=5)),
            "date_end": str(self.today + timedelta(days=5)),
        }

    def get(self, path, extra=None):
        return self.client.get("/api/v1/reports/" + path + "/", {**self.params, **(extra or {})})

    def test_pending_center_boundaries_counts_and_scope(self):
        seventh = create_commitment(
            self.owner, {**self.data, "due_date": self.today + timedelta(days=7)}
        )
        create_commitment(self.owner, {**self.data, "due_date": self.today + timedelta(days=8)})
        self.pending.status = "awaiting_validation"
        self.pending.save()
        response = self.client.get("/api/v1/pending-center/", {"bucket": "upcoming"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["counts"], {"overdue": 1, "upcoming": 2, "validation": 1})
        self.assertEqual(
            {r["id"] for r in response.data["results"]}, {str(self.pending.pk), str(seventh.pk)}
        )
        self.assertIn("no-store", response["Cache-Control"])
        validation = self.client.get("/api/v1/pending-center/", {"bucket": "validation"})
        self.assertEqual(validation.data["count"], 1)
        late = self.client.get("/api/v1/pending-center/")
        self.assertEqual(late.data["results"][0]["id"], str(self.late.pk))
        self.assertNotIn(str(self.hidden.pk), {r["id"] for r in response.data["results"]})

    def test_pending_center_permissions_and_inactive_scope(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/v1/pending-center/").status_code, 403)
        self.client.force_authenticate(self.executor)
        self.assertEqual(self.client.get("/api/v1/pending-center/").data["count"], 1)
        Membership.objects.filter(user=self.executor).delete()
        self.assertEqual(
            self.client.get("/api/v1/pending-center/").data["counts"],
            {"overdue": 0, "upcoming": 0, "validation": 0},
        )
        self.client.force_authenticate(self.admin)
        self.assertEqual(
            self.client.get("/api/v1/pending-center/", {"bucket": "upcoming"}).data["count"], 2
        )
        self.unit.active = False
        self.unit.save()
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.get("/api/v1/pending-center/").data["count"], 0)

    def test_pending_center_validates_parameters_and_paginates(self):
        for params in [{"bucket": "all"}, {"unit": str(self.other.pk)}, {"page": "bad"}]:
            self.assertIn(
                self.client.get("/api/v1/pending-center/", params).status_code, [400, 404]
            )
        for _ in range(50):
            create_commitment(self.owner, {**self.data, "due_date": self.today - timedelta(days=2)})
        response = self.client.get("/api/v1/pending-center/")
        self.assertEqual(response.data["count"], 51)
        self.assertEqual(len(response.data["results"]), 50)
        response = self.client.get("/api/v1/pending-center/", {"page": 2})
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["counts"]["overdue"], 51)

    def test_summary_scope_dedup_denominators_and_empty(self):
        response = self.get("summary")
        self.assertEqual(response.status_code, 200, response.data)
        m = response.data["metrics"]
        self.assertEqual(m["total"], 4)
        self.assertEqual(m["pending"], 2)
        self.assertEqual(m["overdue"], 1)
        self.assertEqual(m["on_time"], 1)
        self.assertEqual(m["completed_known"], 1)
        self.assertEqual(m["on_time_percent"], 100)
        self.assertEqual(m["validation_samples"], 0)
        self.assertIsNone(m["validation_mean_hours"])
        empty = self.get("summary", {"unit": str(self.other.pk)}).data["metrics"]
        self.assertEqual(empty["total"], 0)
        self.assertIsNone(empty["on_time_percent"])
        self.assertIsNone(empty["completion_mean_hours"])
        self.client.force_authenticate(self.executor)
        self.assertEqual(self.get("summary").data["metrics"]["total"], 4)
        self.pending.assignments.filter(user=self.executor).delete()
        self.assertEqual(self.get("summary").data["metrics"]["total"], 3)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.get("summary").data["metrics"]["total"], 5)
        self.unit.active = False
        self.unit.save()
        self.assertEqual(self.get("summary").data["metrics"]["total"], 1)

    def test_combined_filters_and_overdue_periodicity(self):
        self.late.periodicity = "monthly"
        self.late.priority = "high"
        self.late.save()
        result = self.get(
            "occurrences",
            {
                "q": self.late.identifier,
                "assignee": str(self.executor.pk),
                "priority": "high",
                "periodicity": "monthly",
                "overdue": "true",
                "unit": str(self.unit.pk),
                "entity": str(self.entity.pk),
                "category": str(self.category.pk),
                "requester": str(self.owner.pk),
            },
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["count"], 1)
        self.assertEqual(result.data["results"][0]["id"], str(self.late.pk))
        self.assertEqual(self.get("summary", {"overdue": "true"}).data["metrics"]["total"], 1)
        self.assertEqual(self.get("summary", {"status": "completed"}).data["metrics"]["total"], 1)
        self.assertEqual(
            self.get("summary", {"periodicity": "monthly"}).data["metrics"]["recurring"], 1
        )

    def test_time_samples_rejection_latest_submit_and_local_midnight(self):
        start = datetime(2026, 5, 1, 6, tzinfo=ZoneInfo("America/Sao_Paulo"))
        end = start + timedelta(hours=40)
        self.done.created_at = start
        self.done.completed_at = end
        self.done.due_date = end.astimezone(ZoneInfo("America/Sao_Paulo")).date()
        self.done.save()
        # Immutable ledger timestamps are set at insertion by a controlled clock.
        for offset in [2, 30]:
            with patch("django.utils.timezone.now", return_value=start + timedelta(hours=offset)):
                WorkflowTransition.objects.create(
                    occurrence=self.done,
                    actor=self.executor,
                    previous_status="in_progress",
                    new_status="awaiting_validation",
                )
        result = self.get("summary", {"date_start": "2026-05-01", "date_end": "2026-05-05"}).data[
            "metrics"
        ]
        self.assertEqual(result["completion_mean_hours"], 40)
        self.assertEqual(result["validation_mean_hours"], 10)
        self.assertEqual(result["completion_samples"], 1)
        self.assertEqual(result["validation_samples"], 1)
        self.assertEqual(result["on_time_percent"], 100)
        self.done.completed_at = datetime(2026, 5, 3, 2, 59, tzinfo=ZoneInfo("UTC"))
        self.done.save()
        self.assertEqual(
            self.get("summary", {"date_start": "2026-05-01", "date_end": "2026-05-05"}).data[
                "metrics"
            ]["on_time_percent"],
            100,
        )
        self.done.completed_at = datetime(2026, 5, 3, 3, 1, tzinfo=ZoneInfo("UTC"))
        self.done.save()
        self.assertEqual(
            self.get("summary", {"date_start": "2026-05-01", "date_end": "2026-05-05"}).data[
                "metrics"
            ]["on_time_percent"],
            0,
        )

    def test_missing_completion_does_not_inflate_percentage(self):
        self.done.completed_at = None
        self.done.save()
        m = self.get("summary").data["metrics"]
        self.assertEqual(m["completed"], 1)
        self.assertEqual(m["completed_known"], 0)
        self.assertIsNone(m["on_time_percent"])

    def test_group_counts_multi_assignments_no_additive_claim(self):
        for group in ["unit", "entity", "periodicity"]:
            response = self.get("groups", {"group_by": group})
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data["count"], 1)
            self.assertEqual(response.data["results"][0]["total"], 4)
        groups = self.get(
            "groups", {"group_by": "assignee", "assignee": str(self.executor.pk)}
        ).data
        self.assertEqual(groups["count"], 2)
        self.assertEqual(sum(r["total"] for r in groups["results"]), 8)
        self.assertEqual(self.get("groups", {"group_by": "bad"}).status_code, 400)

    def test_pagination_and_export_all_pages(self):
        from apps.commitments.models import CommitmentOccurrence

        CommitmentOccurrence.objects.bulk_create(
            [
                CommitmentOccurrence(
                    definition=self.pending.definition,
                    number=i + 2,
                    identifier=f"{self.pending.definition.identifier}/{i + 2:04d}",
                    title="Page fixture",
                    description="Fictitious",
                    reference_date=self.today,
                    due_date=self.today,
                )
                for i in range(51)
            ]
        )
        page1 = self.get("occurrences")
        page2 = self.get("occurrences", {"page": 2})
        self.assertEqual(page1.data["count"], 55)
        self.assertEqual(len(page1.data["results"]), 50)
        self.assertEqual(len(page2.data["results"]), 5)
        self.assertFalse(
            {o["id"] for o in page1.data["results"]} & {o["id"] for o in page2.data["results"]}
        )
        response = self.get("export")
        self.assertEqual(
            len(list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))),
            56,
        )

    def test_filter_errors_and_anonymous(self):
        for params in [
            {"date_start": "bad"},
            {"date_end": str(self.today - timedelta(days=6))},
            {"date_end": str(self.today + timedelta(days=400))},
            {"unit": "bad"},
            {"overdue": "yes"},
            {"unknown": "x"},
        ]:
            self.assertEqual(self.get("summary", params).status_code, 400)
        self.assertEqual(self.client.get("/api/v1/reports/summary/").status_code, 400)
        self.client.force_authenticate(None)
        self.assertEqual(self.get("summary").status_code, 403)
        self.assertEqual(self.get("export").status_code, 403)

    def test_dashboard_scope_and_month_counts(self):
        response = self.client.get("/api/v1/dashboard/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["completed_this_month"], 1)
        self.assertEqual(response.data["metrics"]["total"], 4)
        self.assertEqual(len(response.data["attention"]), 2)
        self.assertNotIn("Secret Beta", json.dumps(response.data, default=str))

    def test_csv_export_authorization_injection_filters_audit(self):
        self.pending.title = '=HYPERLINK("https://bad.invalid")'
        self.pending.description = 'Line one\nLine two;"quoted"'
        self.pending.custom_values = {"amount": "12345678901234567890.12"}
        self.pending.save()
        response = self.get("export", {"output": "csv", "q": self.pending.identifier})
        self.assertEqual(response.status_code, 200, getattr(response, "data", None))
        self.assertEqual(response["Cache-Control"], "no-store, private")
        data = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(len(data), 2)
        self.assertTrue(data[1][1].startswith("'="))
        self.assertEqual(data[1][2], self.pending.description)
        self.assertIn("12345678901234567890.12", data[1][-1])
        self.assertNotIn("Secret Beta", response.content.decode())
        audit = AuditEvent.objects.get(operation="report.exported")
        self.assertEqual(audit.after["count"], 1)
        self.assertEqual(audit.after["filters"]["q"], self.pending.identifier)
        self.client.force_authenticate(self.stranger)
        response = self.get("export")
        self.assertIn(b"Secret Beta", response.content)
        self.assertNotIn(b"Fictitious report", response.content)

    def test_xlsx_inline_strings_structure_and_atomic_audit_failure(self):
        self.pending.title = "=1+1"
        self.pending.save()
        response = self.get("export", {"output": "xlsx"})
        self.assertEqual(response.status_code, 200, getattr(response, "data", None))
        with ZipFile(io.BytesIO(response.content)) as archive:
            self.assertEqual(len(archive.namelist()), 5)
            for name in archive.namelist():
                ET.fromstring(archive.read(name))
            sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
            ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            self.assertEqual(len(sheet.findall("s:sheetData/s:row", ns)), 5)
            self.assertFalse(sheet.findall(".//s:f", ns))
            self.assertIn("=1+1", archive.read("xl/worksheets/sheet1.xml").decode())
        with patch("apps.reports.views.record", side_effect=RuntimeError("audit failed")):
            with self.assertRaises(RuntimeError):
                self.get("export")
        self.assertEqual(AuditEvent.objects.filter(operation="report.exported").count(), 1)
        self.assertEqual(self.get("export", {"output": "pdf"}).status_code, 400)

    def test_export_limits_no_silent_truncation(self):
        self.pending.custom_values = {"text": "a" * 32768}
        self.pending.save()
        self.assertEqual(self.get("export", {"output": "xlsx"}).status_code, 400)
        self.assertEqual(self.get("export", {"output": "csv"}).status_code, 200)
        with patch("django.db.models.query.QuerySet.count", return_value=5001):
            self.assertEqual(self.get("export").status_code, 400)
        self.assertEqual(column(27), "AA")
        with self.assertRaises(ValidationError):
            xlsx_bytes([["x" * 32768]])
        for value in ["=1", " +1", "-1", "@x", "\tx"]:
            self.assertIn("'", csv_bytes([[value]]).decode())

    def test_favorites_private_validated_audited(self):
        response = self.client.post(
            "/api/v1/report-favorites/",
            {"name": "Fictitious", "filters": {**self.params, "overdue": True}},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        pk = response.data["id"]
        self.assertEqual(
            self.client.post(
                "/api/v1/report-favorites/",
                {"name": "Fictitious", "filters": self.params},
                format="json",
            ).status_code,
            400,
        )
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self.client.get("/api/v1/report-favorites/").data["count"], 0)
        self.assertEqual(
            self.client.delete("/api/v1/report-favorites/" + pk + "/").status_code, 404
        )
        self.client.force_authenticate(self.owner)
        for filters in [{}, {**self.params, "unit": "bad"}, {**self.params, "output": "csv"}]:
            self.assertEqual(
                self.client.post(
                    "/api/v1/report-favorites/", {"name": "Bad", "filters": filters}, format="json"
                ).status_code,
                400,
            )
        self.assertEqual(
            self.client.delete("/api/v1/report-favorites/" + pk + "/").status_code, 204
        )
        self.assertFalse(ReportFavorite.objects.exists())
        self.assertEqual(
            AuditEvent.objects.filter(operation__startswith="report_favorite.").count(), 2
        )

    def test_catalog_updates_admin_concurrency_and_history(self):
        data = {
            "name": "Renamed entity",
            "active": False,
            "expected_name": self.entity.name,
            "expected_active": True,
            "reason": "Fictitious change",
        }
        path = "/api/v1/entities/" + str(self.entity.pk) + "/"
        self.assertEqual(self.client.patch(path, data, format="json").status_code, 403)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.patch(path, data, format="json").status_code, 200)
        self.assertEqual(self.client.patch(path, data, format="json").status_code, 400)
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.definition.entity_id, self.entity.pk)
        self.assertEqual(AuditEvent.objects.filter(operation="catalog.updated").count(), 1)
        self.assertEqual(self.client.delete(path).status_code, 405)
