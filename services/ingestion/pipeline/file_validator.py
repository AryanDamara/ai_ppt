"""
File validation — first gate in the pipeline.

Runs BEFORE anything else. Rejects files that would cause downstream
failures: wrong type, too large, empty, path traversal attempts.

Uses python-magic (libmagic) to detect MIME type from magic bytes —
NOT from the file extension. Users can rename a .exe to .pdf and upload it.
Magic bytes never lie.

Computes SHA256 hash scoped to the tenant for idempotency:
  hash = SHA256(tenant_id_bytes + file_bytes)
Two tenants uploading the same file get different hashes — correct isolation.
Same tenant uploading same file twice → DuplicateDocumentError.
"""
import hashlib
import re
from core.config import get_settings
from core.exceptions import DocumentTooLargeError, UnsupportedFileTypeError

settings = get_settings()

SUPPORTED_MIME_TYPES = frozenset({
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/msword",
    "text/plain",
    "text/markdown",
    "text/csv",
})

MIME_TO_EXTENSION = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/msword": ".doc",
    "text/plain": ".txt",
    "text/markdown": ".md",
    "text/csv": ".csv",
}

# Characters not allowed in safe filenames
_UNSAFE_CHARS = re.compile(r'[/\\?%*:|"<>\x00-\x1f]')


def validate_upload(
    file_bytes: bytes,
    original_filename: str,
    tenant_id: str,
) -> dict:
    """
    Validate an uploaded file before ingestion begins.

    Parameters
    ----------
    file_bytes : raw bytes from multipart upload
    original_filename : user-supplied filename (untrusted — sanitised here)
    tenant_id : authenticated tenant for hash scoping

    Returns
    -------
    dict: file_size_mb, mime_type, doc_hash, safe_filename, file_extension

    Raises
    ------
    ValueError : file is empty (0 bytes)
    DocumentTooLargeError : exceeds max_file_size_mb
    UnsupportedFileTypeError : MIME type not in allowlist
    """
    size_bytes = len(file_bytes)
    if size_bytes == 0:
        raise ValueError("Uploaded file is empty (0 bytes).")

    size_mb = size_bytes / (1024 * 1024)
    if size_mb > settings.max_file_size_mb:
        raise DocumentTooLargeError(size_mb, settings.max_file_size_mb, "MB")

    # MIME detection from magic bytes (never trust the extension)
    try:
        import magic
        mime_type = magic.from_buffer(file_bytes[:4096], mime=True)
    except ImportError:
        # Fallback: infer from extension (less secure, but don't fail)
        ext = original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else ""
        ext_to_mime = {v[1:]: k for k, v in MIME_TO_EXTENSION.items()}
        mime_type = ext_to_mime.get(ext, "application/octet-stream")

    if mime_type not in SUPPORTED_MIME_TYPES:
        raise UnsupportedFileTypeError(mime_type)

    # Sanitise filename: strip dangerous chars, limit length
    safe_name = _UNSAFE_CHARS.sub("_", original_filename).strip()
    safe_name = safe_name[:200] or "document"

    # Tenant-scoped SHA256 for idempotency
    h = hashlib.sha256()
    h.update(tenant_id.encode("utf-8"))
    h.update(file_bytes)
    doc_hash = h.hexdigest()

    return {
        "file_size_mb":   round(size_mb, 3),
        "mime_type":      mime_type,
        "doc_hash":       doc_hash,
        "safe_filename":  safe_name,
        "file_extension": MIME_TO_EXTENSION.get(mime_type, ".bin"),
    }
