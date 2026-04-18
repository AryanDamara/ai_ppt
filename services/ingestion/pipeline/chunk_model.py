"""
Chunk data model — canonical unit of the RAG pipeline.

Design decisions:
  - chunk_id format: "{doc_id}_c{N:04d}" for easy doc-level filtering
  - Pinecone metadata is flat (no nested dicts) per Pinecone's requirements
  - RetrievedChunk carries all scoring signals for debug logging
  - to_citation_dict() maps to Phase 1 JSON schema citations[] array
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ChunkType(str, Enum):
    NARRATIVE_TEXT  = "narrative"           # Paragraphs, sections
    TABLE_JSON      = "table_json"          # Table as structured JSON string
    TABLE_DESC      = "table_description"   # NL description of a table
    CHART_DESC      = "chart_description"   # GPT-4o Vision description of a chart
    IMAGE_DESC      = "image_description"   # Vision description of a general image
    HEADING         = "heading"             # Section header text
    CAPTION         = "caption"             # Figure/table captions
    FOOTNOTE        = "footnote"            # Footnotes and endnotes
    LIST_ITEM       = "list_item"           # Bullet/numbered list items


@dataclass
class ChunkMetadata:
    """
    All metadata stored in Pinecone alongside the vector.
    Pinecone metadata MUST be a flat dict with string/int/float/bool values.
    No nested objects. All lists converted to comma-separated strings.
    """
    chunk_id:        str          # "{doc_id}_c{N:04d}"
    doc_id:          str          # Parent document UUID
    doc_hash:        str          # SHA256 of tenant_id + file_bytes
    tenant_id:       str          # Pinecone namespace filter key

    # Source attribution — written to slide.citations[] in Phase 1
    page_number:     Optional[int]    # 1-indexed; None for DOCX with no page breaks
    section:         Optional[str]    # Nearest parent heading text
    headers_path:    str              # "Executive Summary > Financial Results"
    source_filename: str
    source_uri:      Optional[str]    # S3 URI of original file

    chunk_type:      ChunkType
    language:        str = "en"       # BCP-47 code

    # Structured data links
    links_to:        Optional[str] = None  # JSON snippet (for table_json type)
    image_s3_key:    Optional[str] = None  # S3 key of source image (charts)

    # Quality signals
    token_count:     int  = 0
    char_count:      int  = 0
    pii_redacted:    bool = False

    def to_pinecone_metadata(self) -> dict:
        """
        Flat dict for Pinecone metadata storage.
        IMPORTANT: Pinecone metadata values must be str, int, float, bool, or list[str].
        We convert Optional[int] to int (0 if None) to keep types consistent.
        """
        return {
            "chunk_id":        self.chunk_id,
            "doc_id":          self.doc_id,
            "doc_hash":        self.doc_hash,
            "tenant_id":       self.tenant_id,
            "page_number":     self.page_number or 0,
            "section":         self.section or "",
            "headers_path":    self.headers_path or "",
            "source_filename": self.source_filename,
            "source_uri":      self.source_uri or "",
            "chunk_type":      self.chunk_type.value,
            "language":        self.language,
            "links_to":        (self.links_to or "")[:1000],   # Pinecone 40KB limit
            "image_s3_key":    self.image_s3_key or "",
            "token_count":     self.token_count,
            "char_count":      self.char_count,
            "pii_redacted":    self.pii_redacted,
            # Store chunk text in metadata for BM25-only result reconstruction
            "chunk_text":      "",   # Populated by orchestrator before upsert
        }


@dataclass
class Chunk:
    """Ready-for-embedding unit of document content."""
    text:      str
    metadata:  ChunkMetadata
    embedding: Optional[list[float]] = None

    def __post_init__(self):
        if not self.text or not self.text.strip():
            raise ValueError(f"Empty chunk: {self.metadata.chunk_id}")
        self.metadata.char_count = len(self.text)


@dataclass
class RetrievedChunk:
    """
    Chunk returned from hybrid search, carrying all scoring signals.
    Used to build slide.citations[] in Phase 1.
    """
    chunk_id:     str
    text:         str
    metadata:     dict               # Raw Pinecone metadata
    dense_score:  float = 0.0        # Cosine similarity
    sparse_score: float = 0.0        # BM25 score (normalised)
    fused_score:  float = 0.0        # RRF score
    rerank_score: float = 0.0        # Cross-encoder score (FINAL ordering signal)

    @property
    def page_number(self) -> Optional[int]:
        val = self.metadata.get("page_number", 0)
        return val if val else None

    @property
    def source_filename(self) -> str:
        return self.metadata.get("source_filename", "")

    @property
    def chunk_type(self) -> str:
        return self.metadata.get("chunk_type", "narrative")

    @property
    def doc_id(self) -> str:
        return self.metadata.get("doc_id", "")

    def to_citation_dict(self, confidence_score: float) -> dict:
        """
        Output format for Phase 1 slide.citations[] array.
        Matches the Phase 1 JSON schema citations contract exactly.
        """
        return {
            "source_id":        self.doc_id,
            "chunk_id":         self.chunk_id,
            "page_number":      self.page_number,
            "confidence_score": round(min(1.0, max(0.0, confidence_score)), 4),
            "excerpt":          self.text[:300].strip(),
            "source_filename":  self.source_filename,
        }
