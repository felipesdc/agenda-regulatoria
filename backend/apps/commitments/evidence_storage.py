"""Django Storage contract: private keys only, never public URLs."""

from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from .models import EvidenceBlob


class DatabaseEvidenceStorage(Storage):
    def _save(self, name, content):
        EvidenceBlob.objects.create(id=name, content=content.read())
        return name

    def _open(self, name, mode="rb"):
        if mode != "rb":
            raise ValueError("Evidence storage is read-only after creation")
        return ContentFile(bytes(EvidenceBlob.objects.get(pk=name).content), name=name)

    def exists(self, name):
        return EvidenceBlob.objects.filter(pk=name).exists()

    def delete(self, name):
        raise PermissionError("Evidence is append-only; use logical withdrawal")

    def url(self, name):
        raise PermissionError("Evidence has no public URL")
