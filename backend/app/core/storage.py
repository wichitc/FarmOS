"""File attachment storage (master-prompt integration, Phase 39, SEC-005) -
MinIO was already provisioned as infrastructure since Phase 3 (DEP-001)
but nothing in this platform actually used it until now, so no new
vendor decision was needed. Real validation, not a rubber stamp: an
allowlist of content types (documents/images only, nothing executable)
and a hard size cap, both enforced before a single byte is sent to the
bucket.

First real consumer is support-ticket message attachments
(`routers/v1/crm.py`) - a named gap since Phase 20 ("no file-upload
endpoint exists anywhere in this platform yet").
"""
import uuid
from dataclasses import dataclass
from datetime import timedelta

from fastapi import UploadFile
from minio import Minio

from ..config import settings

ALLOWED_CONTENT_TYPES = {
    "image/png", "image/jpeg", "image/gif", "image/webp",
    "application/pdf",
    "text/plain", "text/csv",
}


class InvalidAttachment(Exception):
    """Raised when an upload fails validation - never reaches MinIO."""


_client: Minio | None = None


def _get_client() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        if not _client.bucket_exists(settings.minio_attachments_bucket):
            _client.make_bucket(settings.minio_attachments_bucket)
    return _client


@dataclass
class StoredAttachment:
    object_key: str
    filename: str
    content_type: str
    size_bytes: int


def upload_attachment(file: UploadFile, *, tenant_id: str) -> StoredAttachment:
    """Validates content-type and size, then uploads to the shared
    attachments bucket under a tenant-prefixed, collision-proof key -
    tenant_id in the key path is a defense-in-depth convention (this
    bucket has no per-tenant access control of its own; every download
    still goes through this platform's own permission checks, not
    MinIO's), not a substitute for the application-level checks the
    caller already does before calling this."""
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise InvalidAttachment(f"Content type '{file.content_type}' is not allowed")

    file.file.seek(0, 2)
    size_bytes = file.file.tell()
    file.file.seek(0)
    if size_bytes > settings.max_attachment_size_bytes:
        raise InvalidAttachment(f"File is {size_bytes} bytes, exceeding the {settings.max_attachment_size_bytes}-byte limit")
    if size_bytes == 0:
        raise InvalidAttachment("File is empty")

    object_key = f"{tenant_id}/{uuid.uuid4().hex}-{file.filename}"
    client = _get_client()
    client.put_object(
        settings.minio_attachments_bucket, object_key, file.file, length=size_bytes, content_type=file.content_type,
    )
    return StoredAttachment(object_key=object_key, filename=file.filename, content_type=file.content_type, size_bytes=size_bytes)


def presigned_download_url(object_key: str) -> str:
    client = _get_client()
    return client.presigned_get_object(settings.minio_attachments_bucket, object_key, expires=timedelta(minutes=15))
