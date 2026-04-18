"""
Tests for the ingestion orchestrator module.

These tests verify the orchestrator's coordination logic with mocked
external dependencies (Docling, OpenAI, Pinecone, Redis).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pipeline.parsers.layout_parser import ParsedElement, ElementType


@pytest.mark.asyncio
async def test_orchestrator_rejects_duplicate_by_hash():
    """Orchestrator should raise DuplicateDocumentError when hash exists in Pinecone."""
    from pipeline.orchestrator import IngestionOrchestrator
    from core.exceptions import DuplicateDocumentError

    with patch.object(IngestionOrchestrator, "__init__", lambda x: None):
        orch = IngestionOrchestrator()
        orch._pinecone = MagicMock()
        orch._pinecone.hash_exists.return_value = "existing-doc-id"
        orch._parser = MagicMock()
        orch._vision = MagicMock()
        orch._pii = MagicMock()
        orch._chunker = MagicMock()
        orch._embedder = MagicMock()

        # mock validate_upload
        with patch("pipeline.orchestrator.validate_upload", return_value={
            "file_size_mb": 0.1,
            "mime_type": "application/pdf",
            "doc_hash": "abc123",
            "safe_filename": "test.pdf",
            "file_extension": ".pdf",
        }):
            with pytest.raises(DuplicateDocumentError):
                await orch.ingest(
                    file_bytes=b"%PDF-1.7\n" + b"0" * 100,
                    original_filename="test.pdf",
                    tenant_id="t-1",
                )


@pytest.mark.asyncio
async def test_orchestrator_rejects_duplicate_by_doc_id():
    """Orchestrator should raise DuplicateDocumentError when doc_id exists."""
    from pipeline.orchestrator import IngestionOrchestrator
    from core.exceptions import DuplicateDocumentError

    with patch.object(IngestionOrchestrator, "__init__", lambda x: None):
        orch = IngestionOrchestrator()
        orch._pinecone = MagicMock()
        orch._pinecone.hash_exists.return_value = None
        orch._pinecone.document_exists.return_value = True
        orch._parser = MagicMock()
        orch._vision = MagicMock()
        orch._pii = MagicMock()
        orch._chunker = MagicMock()
        orch._embedder = MagicMock()

        with patch("pipeline.orchestrator.validate_upload", return_value={
            "file_size_mb": 0.1,
            "mime_type": "application/pdf",
            "doc_hash": "abc123",
            "safe_filename": "test.pdf",
            "file_extension": ".pdf",
        }):
            with pytest.raises(DuplicateDocumentError):
                await orch.ingest(
                    file_bytes=b"%PDF-1.7\n" + b"0" * 100,
                    original_filename="test.pdf",
                    tenant_id="t-1",
                    doc_id="existing-doc",
                )


@pytest.mark.asyncio
async def test_orchestrator_no_chunks_raises():
    """Orchestrator should raise ParseFailedError if no chunks are produced."""
    from pipeline.orchestrator import IngestionOrchestrator
    from core.exceptions import ParseFailedError
    from pipeline.chunk_model import Chunk

    with patch.object(IngestionOrchestrator, "__init__", lambda x: None):
        orch = IngestionOrchestrator()
        orch._pinecone = MagicMock()
        orch._pinecone.hash_exists.return_value = None
        orch._pinecone.document_exists.return_value = False

        # Parser returns elements but chunker returns empty list
        orch._parser = MagicMock()
        orch._parser.parse.return_value = [
            ParsedElement(ElementType.PARAGRAPH, "Some text", 1)
        ]

        orch._pii = MagicMock()
        orch._pii.redact.return_value = MagicMock(
            redacted_text="Some text", pii_found=False, entity_types=[], redaction_count=0
        )

        orch._chunker = MagicMock()
        orch._chunker.chunk.return_value = []   # No chunks produced

        orch._vision = MagicMock()
        orch._embedder = MagicMock()

        with patch("pipeline.orchestrator.validate_upload", return_value={
            "file_size_mb": 0.1,
            "mime_type": "application/pdf",
            "doc_hash": "abc123",
            "safe_filename": "test.pdf",
            "file_extension": ".pdf",
        }):
            with patch("pipeline.orchestrator.markdown_table_to_json", return_value=None):
                with pytest.raises(ParseFailedError):
                    await orch.ingest(
                        file_bytes=b"%PDF-1.7\n" + b"0" * 100,
                        original_filename="test.pdf",
                        tenant_id="t-1",
                    )
