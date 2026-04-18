"""
Shared test fixtures and configuration for the ingestion service test suite.

Provides:
  - Fake file bytes generators (PDF, DOCX magic headers)
  - Mock Pinecone, Redis, and OpenAI clients
  - Sample ParsedElement factories
  - Common test data (tenant IDs, doc IDs, chunk fixtures)
"""
import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

# Ensure the ingestion service root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── File byte generators ─────────────────────────────────────────────────────

def make_fake_pdf(size_mb: float = 0.1) -> bytes:
    """Generate bytes with PDF magic header for testing."""
    header = b"%PDF-1.7\n"
    pad = b"0" * max(0, int(size_mb * 1024 * 1024) - len(header))
    return header + pad


def make_fake_docx() -> bytes:
    """Generate bytes with DOCX (ZIP/OOXML) magic header for testing."""
    # DOCX files are ZIP archives starting with PK magic bytes
    return b"PK\x03\x04" + b"\x00" * 200


def make_fake_txt(content: str = "Sample text document content.") -> bytes:
    """Generate plain text bytes for testing."""
    return content.encode("utf-8")


# ── Test data constants ───────────────────────────────────────────────────────

TEST_TENANT_ID = "test-tenant-001"
TEST_DOC_ID = "doc-test-12345678"
TEST_DOC_HASH = "a" * 64   # Fake SHA256 hash


# ── ParsedElement factories ───────────────────────────────────────────────────

def make_paragraph(text: str, page: int = 1):
    """Create a ParsedElement paragraph for testing."""
    from pipeline.parsers.layout_parser import ParsedElement, ElementType
    return ParsedElement(
        element_type=ElementType.PARAGRAPH,
        text=text,
        page_number=page,
    )


def make_heading(text: str, level: int = 1, page: int = 1):
    """Create a ParsedElement heading for testing."""
    from pipeline.parsers.layout_parser import ParsedElement, ElementType
    elem = ParsedElement(
        element_type=ElementType.HEADING,
        text=text,
        page_number=page,
        heading_level=level,
    )
    elem.section_path = [text]
    return elem


def make_table_element(data: dict, page: int = 1):
    """Create a ParsedElement table for testing."""
    from pipeline.parsers.layout_parser import ParsedElement, ElementType
    elem = ParsedElement(
        element_type=ElementType.TABLE,
        text="",
        page_number=page,
    )
    elem.table_data = data
    return elem


def make_figure_element(image_bytes: bytes = b"\x89PNG" + b"\x00" * 2000, page: int = 1):
    """Create a ParsedElement figure with image bytes for testing."""
    from pipeline.parsers.layout_parser import ParsedElement, ElementType
    return ParsedElement(
        element_type=ElementType.FIGURE,
        text="",
        page_number=page,
        image_bytes=image_bytes,
    )


# ── Chunk factories ───────────────────────────────────────────────────────────

def make_chunk(text: str, chunk_id: str = "doc-test_c0001", chunk_type: str = "narrative"):
    """Create a Chunk object for testing."""
    from pipeline.chunk_model import Chunk, ChunkMetadata, ChunkType
    ct = ChunkType(chunk_type) if chunk_type in [e.value for e in ChunkType] else ChunkType.NARRATIVE_TEXT
    return Chunk(
        text=text,
        metadata=ChunkMetadata(
            chunk_id=chunk_id,
            doc_id=TEST_DOC_ID,
            doc_hash=TEST_DOC_HASH,
            tenant_id=TEST_TENANT_ID,
            page_number=1,
            section=None,
            headers_path="",
            source_filename="test.pdf",
            source_uri="",
            chunk_type=ct,
        ),
    )


def make_retrieved_chunk(
    chunk_id: str = "doc-test_c0001",
    text: str = "Sample retrieved chunk text",
    dense_score: float = 0.85,
    sparse_score: float = 0.7,
    fused_score: float = 0.5,
    rerank_score: float = 0.9,
):
    """Create a RetrievedChunk for testing."""
    from pipeline.chunk_model import RetrievedChunk
    return RetrievedChunk(
        chunk_id=chunk_id,
        text=text,
        metadata={
            "chunk_id": chunk_id,
            "doc_id": TEST_DOC_ID,
            "tenant_id": TEST_TENANT_ID,
            "source_filename": "test.pdf",
            "page_number": 1,
            "chunk_type": "narrative",
        },
        dense_score=dense_score,
        sparse_score=sparse_score,
        fused_score=fused_score,
        rerank_score=rerank_score,
    )


# ── Mock fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def mock_settings():
    """Return a mock settings object with sensible defaults."""
    with patch("core.config.get_settings") as mock:
        s = MagicMock()
        s.pinecone_api_key = "test-key"
        s.pinecone_index_name = "test-index"
        s.pinecone_dimension = 1536
        s.openai_api_key = "test-key"
        s.openai_embedding_model = "text-embedding-3-small"
        s.openai_vision_model = "gpt-4o"
        s.redis_url = "redis://localhost:6379/15"
        s.max_file_size_mb = 50
        s.max_pages_per_document = 500
        s.max_chunk_tokens = 512
        s.chunk_overlap_tokens = 64
        s.min_chunk_tokens = 50
        s.retrieval_top_k_initial = 20
        s.retrieval_top_k_final = 8
        s.min_relevance_score = 0.65
        s.reranker_model = "BAAI/bge-reranker-large"
        s.vision_concurrent_calls = 5
        s.vision_max_retries = 3
        s.pii_redaction_enabled = True
        s.pii_reversible_tokens = True
        s.environment = "test"
        s.log_level = "DEBUG"
        mock.return_value = s
        yield s
