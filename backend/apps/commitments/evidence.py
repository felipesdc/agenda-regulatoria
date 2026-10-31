import hashlib
import io
import re
import socket
import struct
import uuid
import warnings
import unicodedata
import zipfile
from pathlib import PurePosixPath
from xml.etree import ElementTree
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils.module_loading import import_string
from PIL import Image
from pypdf import PdfReader
from rest_framework.exceptions import APIException, ValidationError, PermissionDenied
from apps.audit.services import record
from .models import Evidence, EvidenceWithdrawal, CommitmentOccurrence
from .services import can_execute, can_manage

FORMATS = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "txt": "text/plain",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


class EvidenceUnavailable(APIException):
    status_code = 503
    default_detail = "A inspeção ou o armazenamento do anexo está indisponível. Tente novamente."


def scan(data):
    if not settings.EVIDENCE_SCANNER_HOST:
        if settings.DEBUG:
            return "development:structural_only"
        raise EvidenceUnavailable()
    try:
        with socket.create_connection(
            (settings.EVIDENCE_SCANNER_HOST, settings.EVIDENCE_SCANNER_PORT),
            settings.EVIDENCE_SCANNER_TIMEOUT,
        ) as connection:
            connection.settimeout(settings.EVIDENCE_SCANNER_TIMEOUT)
            connection.sendall(b"zINSTREAM\0")
            for offset in range(0, len(data), 65536):
                chunk = data[offset : offset + 65536]
                connection.sendall(struct.pack("!I", len(chunk)) + chunk)
            connection.sendall(b"\0\0\0\0")
            reply = b""
            while b"\0" not in reply and len(reply) < 2048:
                chunk = connection.recv(256)
                if not chunk:
                    break
                reply += chunk
        if reply == b"stream: OK\0":
            return "clamd:OK"
        if reply.endswith(b" FOUND\0"):
            raise ValidationError({"files": "Anexo recusado pela inspeção antivírus."})
        raise EvidenceUnavailable()
    except OSError as exc:
        raise EvidenceUnavailable() from exc


def check_pdf(data):
    if not data.startswith(b"%PDF-") or not data.rstrip().endswith(b"%%EOF"):
        raise ValueError("Invalid PDF")
    reader = PdfReader(io.BytesIO(data), strict=True)
    if reader.is_encrypted or not 1 <= len(reader.pages) <= 500:
        raise ValueError("Encrypted or oversized PDF")
    forbidden = {
        "/JS",
        "/JavaScript",
        "/Launch",
        "/EmbeddedFile",
        "/EmbeddedFiles",
        "/OpenAction",
        "/AA",
        "/RichMedia",
        "/XFA",
        "/SubmitForm",
        "/ImportData",
        "/GoToE",
    }
    seen = set()
    budget = [10000]

    def visit(obj, depth=0):
        if depth > 30 or budget[0] <= 0:
            raise ValueError("Complex PDF")
        if hasattr(obj, "get_object"):
            obj = obj.get_object()
        if id(obj) in seen:
            return
        seen.add(id(obj))
        budget[0] -= 1
        if isinstance(obj, str) and obj in forbidden:
            raise ValueError("Active PDF action")
        if isinstance(obj, dict):
            if forbidden.intersection(str(key) for key in obj):
                raise ValueError("Active PDF")
            for value in obj.values():
                visit(value, depth + 1)
        elif isinstance(obj, (list, tuple)):
            for value in obj:
                visit(value, depth + 1)

    visit(reader.trailer)


def check_office(data, extension):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos = archive.infolist()
        names = [item.filename for item in infos]
        if (
            len(infos) > 200
            or len(names) != len(set(names))
            or sum(item.file_size for item in infos) > 8 * 1024 * 1024
        ):
            raise ValueError("Archive limits")
        expected = "word/document.xml" if extension == "docx" else "xl/workbook.xml"
        if (
            expected not in names
            or "[Content_Types].xml" not in names
            or "_rels/.rels" not in names
            or ("word/document.xml" in names and "xl/workbook.xml" in names)
        ):
            raise ValueError("Wrong Office container")
        for item in infos:
            path = PurePosixPath(item.filename)
            lower = item.filename.lower()
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in lower
                or item.compress_type not in [zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED]
                or item.flag_bits & 1
                or item.file_size > 2 * 1024 * 1024
            ):
                raise ValueError("Unsafe archive entry")
            if any(
                term in lower
                for term in [
                    "vbaproject",
                    "embeddings/",
                    "activex",
                    "customui",
                    "externallinks/",
                    "connections.xml",
                    "querytables/",
                    "macrosheets/",
                ]
            ):
                raise ValueError("Active Office content")
            if not lower.endswith((".xml", ".rels", ".png", ".jpg", ".jpeg")) and not item.is_dir():
                raise ValueError("Unsupported embedded content")
            content = archive.read(item)
            if lower.endswith((".xml", ".rels")):
                text = content.decode("utf-8-sig")
                if "\0" in text or "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
                    raise ValueError("Unsafe XML")
                root = ElementTree.fromstring(text)
                if item.filename == expected:
                    expected_tag = (
                        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}document"
                        if extension == "docx"
                        else "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}workbook"
                    )
                    if root.tag != expected_tag:
                        raise ValueError("Wrong Office root")
                if item.filename == "[Content_Types].xml":
                    kind = (
                        "wordprocessingml.document"
                        if extension == "docx"
                        else "spreadsheetml.sheet"
                    )
                    if not any(
                        node.attrib.get("PartName") == "/" + expected
                        and node.attrib.get("ContentType")
                        == "application/vnd.openxmlformats-officedocument." + kind + ".main+xml"
                        for node in root
                    ):
                        raise ValueError("Wrong Office content type")
                if item.filename == "_rels/.rels" and not any(
                    node.attrib.get("Type", "").endswith("/officeDocument")
                    and node.attrib.get("Target", "").lstrip("/") == expected
                    for node in root
                ):
                    raise ValueError("Missing main relationship")
                for node in root.iter():
                    local = node.tag.rsplit("}", 1)[-1]
                    if local in ["f", "instrText"] and re.search(
                        r"(?i)\b(WEBSERVICE|HYPERLINK|RTD|CALL|REGISTER|EXEC|DDEAUTO|DDE|INCLUDETEXT|INCLUDEPICTURE)\b|\|",
                        (node.text or "")
                        + " ".join(
                            value
                            for key, value in node.attrib.items()
                            if key.rsplit("}", 1)[-1] == "instr"
                        ),
                    ):
                        raise ValueError("Active document field")
                if any(node.attrib.get("TargetMode") == "External" for node in root.iter()):
                    raise ValueError("External Office relationship")
                if "macroenabled" in text.lower() or "macrosheet" in text.lower():
                    raise ValueError("Macro document")


def prepare_files(files):
    if len(files) > settings.EVIDENCE_MAX_FILES:
        raise ValidationError(
            {"files": f"Envie no máximo {settings.EVIDENCE_MAX_FILES} arquivos por providência."}
        )
    prepared = []
    total = 0
    for upload in files:
        name = unicodedata.normalize("NFC", upload.name)
        if (
            any(unicodedata.category(char) in ["Cc", "Cf"] for char in name)
            or len(name) > 180
            or re.search(r"[\x00-\x1f\x7f/\\]", name)
            or name.startswith(".")
        ):
            raise ValidationError({"files": "Nome de arquivo inválido."})
        extension = name.rsplit(".", 1)[-1].lower()
        if extension not in FORMATS or not 0 < upload.size <= settings.EVIDENCE_MAX_FILE_BYTES:
            raise ValidationError(
                {"files": "Formato não permitido, arquivo vazio ou tamanho acima do limite."}
            )
        data = upload.read(settings.EVIDENCE_MAX_FILE_BYTES + 1)
        total += len(data)
        if len(data) != upload.size or total > 10 * 1024 * 1024:
            raise ValidationError({"files": "Limite de envio excedido."})
        try:
            if extension == "pdf":
                check_pdf(data)
            elif extension in ["docx", "xlsx"]:
                check_office(data, extension)
            elif extension == "txt":
                text = data.decode("utf-8-sig")
                if any(ord(char) < 32 and char not in "\t\n\r" for char in text):
                    raise ValueError("Binary text")
            else:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    with Image.open(io.BytesIO(data)) as image:
                        if (
                            image.format != ("PNG" if extension == "png" else "JPEG")
                            or image.width * image.height > 20000000
                            or getattr(image, "n_frames", 1) != 1
                        ):
                            raise ValueError("Image limits")
                        image.verify()
                    with Image.open(io.BytesIO(data)) as image:
                        image.load()
        except Exception as exc:
            raise ValidationError(
                {"files": f"Conteúdo inválido ou não permitido em {name}."}
            ) from exc
        prepared.append(
            {
                "filename": name,
                "media_type": FORMATS[extension],
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "inspection": scan(data),
                "data": data,
            }
        )
    return prepared


def store_files(actor, action, files):
    backend = settings.EVIDENCE_STORAGE_BACKEND
    storage = import_string(backend)()
    for item in files:
        values = dict(item)
        data = values.pop("data")
        key = storage.save(uuid.uuid4().hex, ContentFile(data))
        evidence = Evidence.objects.create(
            action=action, storage_key=key, storage_backend=backend, **values
        )
        record(
            actor,
            "evidence.uploaded",
            evidence,
            action.occurrence.definition.unit,
            after={
                "action": str(action.pk),
                "occurrence": str(action.occurrence_id),
                **{key: values[key] for key in ["filename", "size", "sha256", "inspection"]},
            },
        )


@transaction.atomic
def withdraw(actor, evidence, reason):
    occurrence = (
        CommitmentOccurrence.objects.select_for_update()
        .select_related("definition__unit", "definition__requester")
        .get(pk=evidence.action.occurrence_id)
    )
    if not (
        can_execute(actor, occurrence)
        and evidence.action.author_id == actor.pk
        or can_manage(actor, occurrence)
    ):
        raise PermissionDenied("Sem permissão para retirar esta evidência.")
    if occurrence.status not in ["pending", "in_progress", "rejected"]:
        raise ValidationError("A evidência não pode ser retirada neste estado do compromisso.")
    if EvidenceWithdrawal.objects.filter(evidence=evidence).exists():
        raise ValidationError("Evidência já retirada.")
    EvidenceWithdrawal.objects.create(evidence=evidence, actor=actor, reason=reason)
    record(
        actor,
        "evidence.withdrawn",
        evidence,
        occurrence.definition.unit,
        after={"sha256": evidence.sha256, "occurrence": str(occurrence.pk)},
        reason=reason,
    )
