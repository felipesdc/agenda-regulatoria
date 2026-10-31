import hashlib
import io
import socket
import struct
import threading
import zipfile
from unittest.mock import patch
from django.db import DatabaseError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from PIL import Image
from pypdf import PdfWriter
from apps.accounts.models import User, Membership
from apps.organizations.models import OrganizationalUnit
from apps.audit.models import AuditEvent
from .models import (
    IdentifierCounter,
    CommitmentCategory,
    RegulatoryEntity,
    Evidence,
    EvidenceBlob,
    EvidenceWithdrawal,
)
from .services import create_commitment
from .evidence import scan, EvidenceUnavailable
from .evidence_storage import DatabaseEvidenceStorage


@override_settings(DEBUG=True, EVIDENCE_SCANNER_HOST="")
class EvidenceTests(TestCase):
    def setUp(self):
        IdentifierCounter.objects.get_or_create(name="commitment")
        self.owner = User.objects.create_user("ev_owner")
        self.executor = User.objects.create_user("ev_executor")
        self.stranger = User.objects.create_user("ev_stranger")
        self.admin = User.objects.create_superuser("ev_admin")
        self.unit = OrganizationalUnit.objects.create(code="ev", name="Evidence")
        Membership.objects.create(user=self.owner, unit=self.unit, role="requester")
        Membership.objects.create(user=self.executor, unit=self.unit, role="executor")
        self.row = create_commitment(
            self.owner,
            {
                "title": "Fictitious evidence",
                "description": "Test",
                "unit": self.unit,
                "entity": RegulatoryEntity.objects.create(name="Evidence entity"),
                "category": CommitmentCategory.objects.create(name="Evidence category"),
                "assignees": [self.executor],
                "reference_date": timezone.localdate(),
                "due_date": timezone.localdate(),
                "priority": "normal",
            },
        )
        self.row.status = "in_progress"
        self.row.save()
        self.client = APIClient()
        self.client.force_authenticate(self.executor)
        self.path = f"/api/v1/occurrences/{self.row.pk}/actions/"

    def upload(self, data=b"Fictitious evidence\n", name="evidência.txt", **extra):
        return self.client.post(
            self.path,
            {
                "text": "Conferência fictícia",
                "files": [SimpleUploadedFile(name, data, "application/octet-stream")],
                **extra,
            },
            format="multipart",
        )

    def test_upload_download_hash_scope_and_audit(self):
        response = self.upload()
        self.assertEqual(response.status_code, 201, response.data)
        file = response.data["evidence"][0]
        self.assertEqual(file["sha256"], hashlib.sha256(b"Fictitious evidence\n").hexdigest())
        self.assertNotIn("storage_key", file)
        self.assertNotIn("content", file)
        path = f"/api/v1/evidence/{file['id']}/download/"
        response = self.client.get(path)
        self.assertEqual(response.content, b"Fictitious evidence\n")
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self.client.get(path).status_code, 404)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(path).status_code, 403)
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.get(path).status_code, 200)
        Membership.objects.filter(user=self.executor).delete()
        self.client.force_authenticate(self.executor)
        self.assertEqual(self.client.get(path).status_code, 404)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(path).status_code, 200)
        self.unit.active = False
        self.unit.save()
        self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(AuditEvent.objects.filter(operation="evidence.uploaded").count(), 1)
        self.assertEqual(AuditEvent.objects.filter(operation="evidence.downloaded").count(), 3)

    def test_atomic_rejection_limits_and_non_executor(self):
        for data, name in [
            (b"MZfake", "fake.pdf"),
            (b"", "empty.txt"),
            (b"<svg/>", "file.svg"),
            (b"\0binary", "file.txt"),
            (b"PKfake", "fake.docx"),
        ]:
            self.assertEqual(self.upload(data, name).status_code, 400)
        with override_settings(EVIDENCE_MAX_FILE_BYTES=2):
            self.assertEqual(self.upload().status_code, 400)
        self.assertEqual(
            self.client.post(
                self.path,
                {"text": "Test", "files": [SimpleUploadedFile(f"{i}.txt", b"a") for i in range(4)]},
                format="multipart",
            ).status_code,
            400,
        )
        self.assertFalse(self.row.actions.exists())
        self.assertFalse(Evidence.objects.exists())
        self.assertFalse(EvidenceBlob.objects.exists())
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.upload().status_code, 403)
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self.upload().status_code, 404)
        self.client.force_authenticate(self.executor)
        self.row.status = "completed"
        self.row.save()
        self.assertEqual(self.upload().status_code, 400)

    def test_withdrawal_is_logical_justified_and_state_protected(self):
        file = self.upload().data["evidence"][0]
        path = f"/api/v1/evidence/{file['id']}/withdraw/"
        self.assertEqual(self.client.post(path, {"reason": ""}).status_code, 400)
        self.row.status = "awaiting_validation"
        self.row.save()
        self.assertEqual(self.client.post(path, {"reason": "Correção"}).status_code, 400)
        self.row.status = "in_progress"
        self.row.save()
        response = self.client.post(path, {"reason": "Documento anexado por engano"})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["withdrawn"])
        self.assertEqual(
            self.client.get(f"/api/v1/evidence/{file['id']}/download/").status_code, 410
        )
        self.assertEqual(self.client.post(path, {"reason": "Outra retirada"}).status_code, 400)
        self.assertEqual(EvidenceBlob.objects.count(), 1)
        self.assertEqual(EvidenceWithdrawal.objects.count(), 1)
        self.assertEqual(AuditEvent.objects.filter(operation="evidence.withdrawn").count(), 1)

    def test_immutable_history_and_integrity_failure(self):
        evidence = Evidence.objects.get(pk=self.upload().data["evidence"][0]["id"])
        for model, field, value in [
            (Evidence, "filename", "changed.txt"),
            (EvidenceBlob, "content", b"changed"),
        ]:
            with self.assertRaises(DatabaseError), transaction.atomic():
                model.objects.all().update(**{field: value})
            with self.assertRaises(DatabaseError), transaction.atomic():
                model.objects.all().delete()
        with patch.object(DatabaseEvidenceStorage, "_open", return_value=io.BytesIO(b"corrupted")):
            self.assertEqual(
                self.client.get(f"/api/v1/evidence/{evidence.pk}/download/").status_code, 503
            )
        self.assertFalse(AuditEvent.objects.filter(operation="evidence.downloaded").exists())
        with self.assertRaises(PermissionError):
            DatabaseEvidenceStorage().url(evidence.storage_key)

    def test_production_requires_antivirus_and_rolls_back_failure(self):
        with override_settings(DEBUG=False):
            self.assertEqual(self.upload().status_code, 503)
        with patch("apps.commitments.evidence.scan", side_effect=EvidenceUnavailable()):
            self.assertEqual(self.upload().status_code, 503)
        with patch("apps.commitments.evidence.record", side_effect=RuntimeError("audit failure")):
            with self.assertRaises(RuntimeError):
                self.upload()
        self.assertFalse(EvidenceBlob.objects.exists())
        self.assertFalse(self.row.actions.exists())
        file = self.upload().data["evidence"][0]
        with override_settings(DEBUG=False):
            self.assertEqual(
                self.client.get(f"/api/v1/evidence/{file['id']}/download/").status_code, 503
            )

    def test_occurrence_quota_includes_withdrawn_files(self):
        with override_settings(EVIDENCE_MAX_OCCURRENCE_FILES=1):
            file = self.upload().data["evidence"][0]
            self.client.post(f"/api/v1/evidence/{file['id']}/withdraw/", {"reason": "Correção"})
            self.assertEqual(self.upload().status_code, 400)
            self.assertEqual(self.row.actions.count(), 1)
        with override_settings(EVIDENCE_MAX_OCCURRENCE_BYTES=1):
            self.assertEqual(self.upload().status_code, 400)

    def test_real_pdf_images_and_office_validation(self):
        pdf = io.BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.write(pdf)
        active_pdf = io.BytesIO()
        active_writer = PdfWriter()
        active_writer.add_blank_page(width=100, height=100)
        active_writer.add_js("app.alert('Fictitious test')")
        active_writer.write(active_pdf)
        self.assertEqual(self.upload(active_pdf.getvalue(), "active.pdf").status_code, 400)
        png = io.BytesIO()
        Image.new("RGB", (2, 2)).save(png, format="PNG")
        from apps.reports.exports import xlsx_bytes

        # Use the application's own bounded XLSX writer as a real Office fixture.
        xlsx = xlsx_bytes([["Heading"], ["A"]])
        for name, data in [
            ("document.pdf", pdf.getvalue()),
            ("image.png", png.getvalue()),
            ("sheet.xlsx", xlsx),
        ]:
            self.assertEqual(self.upload(data, name).status_code, 201)
        docx = io.BytesIO()
        with zipfile.ZipFile(docx, "w") as z:
            z.writestr(
                "[Content_Types].xml",
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
            )
            z.writestr(
                "_rels/.rels",
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
            )
            z.writestr(
                "word/document.xml",
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p/></w:body></w:document>',
            )
        self.assertEqual(self.upload(docx.getvalue(), "document.docx").status_code, 201)
        # Container validation rejects generic ZIP files pretending to be Office documents.
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("word/document.xml", "<fake/>")
        self.assertEqual(self.upload(archive.getvalue(), "bad.docx").status_code, 400)


class ScannerProtocolTests(TestCase):
    def test_real_socket_stream_protocol_accepts_clean_and_rejects_errors(self):
        for reply, expected in [
            (b"stream: OK\0", None),
            (b"stream: Eicar FOUND\0", 400),
            (b"stream: ERROR\0", 503),
        ]:
            server = socket.socket()
            server.bind(("127.0.0.1", 0))
            server.listen(1)
            port = server.getsockname()[1]
            received = []

            def run():
                with server:
                    connection, _ = server.accept()
                    with connection:

                        def exact(size):
                            data = b""
                            while len(data) < size:
                                data += connection.recv(size - len(data))
                            return data

                        self.assertEqual(exact(10), b"zINSTREAM\0")
                        while True:
                            size = struct.unpack("!I", exact(4))[0]
                            if not size:
                                break
                            received.append(exact(size))
                        connection.sendall(reply)

            thread = threading.Thread(target=run, daemon=True)
            thread.start()
            with override_settings(EVIDENCE_SCANNER_HOST="127.0.0.1", EVIDENCE_SCANNER_PORT=port):
                if expected:
                    from rest_framework.exceptions import APIException

                    with self.assertRaises(APIException) as error:
                        scan(b"test stream")
                    self.assertEqual(error.exception.status_code, expected)
                else:
                    self.assertEqual(scan(b"test stream"), "clamd:OK")
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(b"".join(received), b"test stream")
