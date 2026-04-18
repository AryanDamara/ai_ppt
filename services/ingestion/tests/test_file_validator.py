import pytest
from pipeline.file_validator import validate_upload
from core.exceptions import DocumentTooLargeError, UnsupportedFileTypeError


def make_fake_pdf(size_mb: float) -> bytes:
    """Make bytes that look like a PDF magic header + padding."""
    header = b"%PDF-1.7\n"
    pad    = b"0" * int(size_mb * 1024 * 1024 - len(header))
    return header + pad


def test_valid_pdf_passes():
    file_bytes = make_fake_pdf(0.5)
    result     = validate_upload(file_bytes, "report.pdf", "tenant-123")
    assert result["mime_type"] == "application/pdf"
    assert result["file_size_mb"] < 1.0
    assert len(result["doc_hash"]) == 64   # SHA256 hex


def test_empty_file_raises():
    with pytest.raises(ValueError, match="empty"):
        validate_upload(b"", "empty.pdf", "tenant-123")


def test_file_too_large_raises():
    file_bytes = make_fake_pdf(60.0)   # Exceeds 50MB limit
    with pytest.raises(DocumentTooLargeError):
        validate_upload(file_bytes, "big.pdf", "tenant-123")


def test_unsupported_mime_raises():
    # .exe magic bytes (MZ header)
    exe_bytes = b"MZ" + b"\x00" * 100
    with pytest.raises(UnsupportedFileTypeError):
        validate_upload(exe_bytes, "malware.exe", "tenant-123")


def test_same_file_different_tenants_different_hashes():
    """Hash must be tenant-scoped — same content, different tenants → different hashes."""
    file_bytes = make_fake_pdf(0.1)
    h1 = validate_upload(file_bytes, "f.pdf", "tenant-aaa")["doc_hash"]
    h2 = validate_upload(file_bytes, "f.pdf", "tenant-bbb")["doc_hash"]
    assert h1 != h2


def test_filename_sanitisation():
    """Dangerous filenames must be sanitised."""
    file_bytes = make_fake_pdf(0.1)
    result     = validate_upload(file_bytes, "../../../etc/passwd.pdf", "t-123")
    assert ".." not in result["safe_filename"]
    assert "/" not in result["safe_filename"]
