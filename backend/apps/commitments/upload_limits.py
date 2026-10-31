"""Stop multipart uploads before oversized files reach memory or temporary storage."""

from django.conf import settings
from django.core.files.uploadhandler import FileUploadHandler, StopUpload
from django.core.exceptions import RequestDataTooBig


class EvidenceUploadLimits(FileUploadHandler):
    def __init__(self, request=None):
        super().__init__(request)
        self.total = 0
        self.current = 0
        self.count = 0

    def handle_raw_input(self, input_data, META, content_length, boundary, encoding=None):
        if content_length and content_length > 12 * 1024 * 1024:
            raise RequestDataTooBig("Upload request exceeds limit")

    def new_file(self, *args, **kwargs):
        super().new_file(*args, **kwargs)
        self.current = 0
        self.count += 1
        if self.count > settings.EVIDENCE_MAX_FILES:
            self.stop()

    def stop(self):
        self.request.evidence_upload_error = True
        raise StopUpload(connection_reset=True)

    def receive_data_chunk(self, raw_data, start):
        self.current += len(raw_data)
        self.total += len(raw_data)
        if self.current > settings.EVIDENCE_MAX_FILE_BYTES or self.total > 10 * 1024 * 1024:
            self.stop()
        return raw_data

    def file_complete(self, file_size):
        return None
