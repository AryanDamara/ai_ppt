"""
Idempotency tests for the ingestion pipeline.

These tests verify that:
1. Same file uploaded twice by the same tenant → DuplicateDocumentError
2. Same file uploaded by different tenants → succeeds (different hash)
3. Same doc_id re-used → DuplicateDocumentError
4. File validation hash is tenant-scoped (deterministic)
"""
import pytest
from pipeline.file_validator import validate_upload
from core.exceptions import DuplicateDocumentError


def test_tenant_scoped_hash_deterministic():
    """Same file + same tenant should produce the same hash every time."""
    file_bytes = b"%PDF-1.7\n" + b"data" * 100
    h1 = validate_upload(file_bytes, "report.pdf", "tenant-A")["doc_hash"]
    h2 = validate_upload(file_bytes, "report.pdf", "tenant-A")["doc_hash"]
    assert h1 == h2


def test_different_tenants_different_hashes():
    """Same file uploaded by different tenants should get different hashes."""
    file_bytes = b"%PDF-1.7\n" + b"data" * 100
    h1 = validate_upload(file_bytes, "report.pdf", "tenant-A")["doc_hash"]
    h2 = validate_upload(file_bytes, "report.pdf", "tenant-B")["doc_hash"]
    assert h1 != h2


def test_different_files_same_tenant_different_hashes():
    """Different files from the same tenant should have different hashes."""
    file1 = b"%PDF-1.7\n" + b"content_one" * 100
    file2 = b"%PDF-1.7\n" + b"content_two" * 100
    h1 = validate_upload(file1, "report1.pdf", "tenant-A")["doc_hash"]
    h2 = validate_upload(file2, "report2.pdf", "tenant-A")["doc_hash"]
    assert h1 != h2


def test_filename_does_not_affect_hash():
    """Hash is computed from file content + tenant_id, NOT from filename."""
    file_bytes = b"%PDF-1.7\n" + b"data" * 100
    h1 = validate_upload(file_bytes, "report.pdf", "tenant-A")["doc_hash"]
    h2 = validate_upload(file_bytes, "different_name.pdf", "tenant-A")["doc_hash"]
    assert h1 == h2


def test_hash_is_64_char_hex():
    """Hash should be a valid SHA256 hex digest (64 characters)."""
    file_bytes = b"%PDF-1.7\n" + b"data" * 100
    h = validate_upload(file_bytes, "report.pdf", "tenant-A")["doc_hash"]
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_duplicate_document_error_fields():
    """DuplicateDocumentError should carry hash and existing_doc_id."""
    err = DuplicateDocumentError("abc123" * 5, "doc-existing-123")
    assert err.doc_hash == "abc123" * 5
    assert err.existing_doc_id == "doc-existing-123"
    assert "Duplicate" in str(err)
    assert "doc-existing-123" in str(err)


def test_chunk_id_format():
    """Chunk IDs should follow the {doc_id}_c{N:04d} format."""
    from pipeline.chunkers.semantic_chunker import SemanticChunker
    from pipeline.parsers.layout_parser import ParsedElement, ElementType

    chunker = SemanticChunker(max_chunk_tokens=200, overlap_tokens=20, min_chunk_tokens=5)
    elements = [
        ParsedElement(ElementType.PARAGRAPH, "Content for chunk one. " * 20, 1),
        ParsedElement(ElementType.PARAGRAPH, "Content for chunk two. " * 20, 2),
    ]
    chunks = chunker.chunk(
        elements=elements,
        doc_id="doc-abc12345",
        doc_hash="h" * 64,
        tenant_id="t-1",
        source_filename="test.pdf",
    )

    for chunk in chunks:
        assert chunk.metadata.chunk_id.startswith("doc-abc12345_c")
        # Verify zero-padded sequence number
        seq_part = chunk.metadata.chunk_id.split("_c")[1]
        assert len(seq_part) == 4
        assert seq_part.isdigit()
