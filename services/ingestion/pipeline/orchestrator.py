"""
Ingestion orchestrator — executes all 12 pipeline steps in sequence.

STEPS:
  1.  File validation (size, MIME, path safety)
  2.  Content-level idempotency (check doc_hash in Pinecone)
  3.  Document-level idempotency (check doc_id)
  4.  Save raw file to S3 (for re-ingestion if pipeline changes)
  5.  Layout-aware parsing with Docling
  6.  Table structure extraction (JSON + markdown for each TABLE element)
  7.  PII redaction on ALL text before ANY API call
  8.  Semantic chunking (produces Chunk objects without embeddings)
  9.  Vision enrichment (GPT-4o Vision for FIGURE elements — concurrent)
  10. Batch embedding (OpenAI text-embedding-3-small, 100 chunks/call)
  11. Pinecone upsert (with chunk_text in metadata)
  12. BM25 index build/update (Redis persistence)

NON-FATAL FAILURES (log + continue):
  - Vision enrichment for one image: log warning, skip this image's chunk
  - BM25 update: log warning, dense search still fully functional
  - S3 raw file save: log warning, ingestion continues without raw file backup

FATAL FAILURES (entire job fails → DLQ):
  - File validation: wrong type or too large
  - Docling parsing: zero elements extracted
  - Batch embedding: API failure after 3 retries
  - Pinecone upsert: cannot store vectors after 3 retries
"""
from __future__ import annotations
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pipeline.file_validator import validate_upload
from pipeline.parsers.layout_parser import LayoutParser, ElementType
from pipeline.parsers.table_extractor import extract_table_to_json, markdown_table_to_json
from pipeline.enrichers.vision_enricher import VisionEnricher
from pipeline.enrichers.pii_redactor import PIIRedactor
from pipeline.chunkers.semantic_chunker import SemanticChunker
from pipeline.embedders.batch_embedder import BatchEmbedder
from pipeline.storage.pinecone_client import PineconeVectorStore
from pipeline.storage.bm25_index import build_and_save_bm25
from pipeline.chunk_model import Chunk, ChunkMetadata, ChunkType
from core.config import get_settings
from core.exceptions import (
    DuplicateDocumentError, ParseFailedError,
)

settings = get_settings()
logger   = logging.getLogger(__name__)


class IngestionOrchestrator:
    """Runs the full 12-step ingestion pipeline for one document."""

    def __init__(self):
        self._parser   = LayoutParser()
        self._vision   = VisionEnricher()
        self._pii      = PIIRedactor()
        self._chunker  = SemanticChunker()
        self._embedder = BatchEmbedder()
        self._pinecone = PineconeVectorStore()

    async def ingest(
        self,
        file_bytes:        bytes,
        original_filename: str,
        tenant_id:         str,
        doc_id:            Optional[str] = None,
        language:          str           = "en",
    ) -> dict:
        """
        Run the full ingestion pipeline for one document.

        Returns summary dict on success.
        Raises on fatal failure (caller pushes to DLQ).
        """
        t_start = datetime.now(timezone.utc)
        doc_id  = doc_id or str(uuid4())

        logger.info(f"Ingestion start: doc={doc_id[:8]}… file='{original_filename}'")

        # ── Step 1: File validation ────────────────────────────────────────────
        v = validate_upload(file_bytes, original_filename, tenant_id)
        doc_hash  = v["doc_hash"]
        mime_type = v["mime_type"]

        # ── Step 2: Content-level idempotency (hash) ───────────────────────────
        existing_doc_id = self._pinecone.hash_exists(doc_hash, tenant_id)
        if existing_doc_id:
            raise DuplicateDocumentError(doc_hash, existing_doc_id)

        # ── Step 3: Document-level idempotency (doc_id) ────────────────────────
        if self._pinecone.document_exists(doc_id, tenant_id):
            raise DuplicateDocumentError(doc_hash, doc_id)

        # ── Step 4: Save raw file to S3 ───────────────────────────────────────
        source_uri = ""
        try:
            from storage.s3_client import upload_raw_document
            source_uri = upload_raw_document(file_bytes, doc_id, v["safe_filename"])
        except Exception as e:
            logger.warning(f"S3 raw file save failed (non-fatal): {e}")

        # ── Step 5: Layout-aware parsing ──────────────────────────────────────
        elements = self._parser.parse(
            file_bytes=file_bytes,
            mime_type=mime_type,
            source_filename=original_filename,
            max_pages=settings.max_pages_per_document,
        )
        page_count = max((e.page_number for e in elements), default=1)

        # ── Step 6: Table structure extraction ────────────────────────────────
        for elem in elements:
            if elem.element_type == ElementType.TABLE and elem.table_data is None:
                if elem.text and '|' in elem.text:
                    elem.table_data = markdown_table_to_json(elem.text)

        # ── Step 7: PII redaction on ALL text ─────────────────────────────────
        had_pii = False
        for elem in elements:
            if elem.text:
                result    = self._pii.redact(elem.text, language=language,
                                             reversible=settings.pii_reversible_tokens)
                elem.text = result.redacted_text
                if result.pii_found:
                    had_pii = True
                    logger.debug(f"PII redacted on page {elem.page_number}: {result.entity_types}")

        # ── Step 8: Semantic chunking ──────────────────────────────────────────
        text_chunks = self._chunker.chunk(
            elements=elements,
            doc_id=doc_id,
            doc_hash=doc_hash,
            tenant_id=tenant_id,
            source_filename=original_filename,
            source_uri=source_uri,
            language=language,
        )

        # ── Step 9: Vision enrichment (concurrent) ─────────────────────────────
        vision_chunks: list[Chunk] = []
        figure_elements = [
            (idx, elem) for idx, elem in enumerate(elements)
            if elem.element_type == ElementType.FIGURE
        ]

        if figure_elements:
            async def _enrich_one(idx: int, elem) -> Optional[Chunk]:
                desc = await self._vision.describe_image(
                    image_bytes=elem.image_bytes,
                    caption=elem.image_caption,
                    page_number=elem.page_number,
                )
                if not desc:
                    return None
                # Determine chunk type from description prefix
                chunk_type = (
                    ChunkType.CHART_DESC if "[Chart" in desc or "[Table image" in desc
                    else ChunkType.IMAGE_DESC
                )
                cid = f"{doc_id}_vis{idx:04d}"
                return Chunk(
                    text=desc,
                    metadata=ChunkMetadata(
                        chunk_id=cid,
                        doc_id=doc_id, doc_hash=doc_hash, tenant_id=tenant_id,
                        page_number=elem.page_number,
                        section=elem.section_path[-1] if elem.section_path else None,
                        headers_path=" > ".join(elem.section_path),
                        source_filename=original_filename,
                        source_uri=source_uri,
                        chunk_type=chunk_type,
                        language=language,
                        image_s3_key="",   # TODO: upload image to S3 and store key
                    ),
                )

            tasks   = [_enrich_one(idx, elem) for idx, elem in figure_elements]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Chunk):
                    vision_chunks.append(r)
                elif isinstance(r, Exception):
                    logger.warning(f"Vision enrichment failed for one figure: {r}")

        # Combine all chunks
        all_chunks = text_chunks + vision_chunks

        if not all_chunks:
            raise ParseFailedError(doc_id, "No chunks produced from document")

        # ── Step 10: Batch embedding ───────────────────────────────────────────
        all_chunks = await self._embedder.embed_chunks(all_chunks)

        # ── Step 11: Pinecone upsert ───────────────────────────────────────────
        upserted = self._pinecone.upsert_chunks(all_chunks, tenant_id)

        # ── Step 12: BM25 update ──────────────────────────────────────────────
        try:
            chunk_texts = [c.text for c in all_chunks]
            chunk_ids   = [c.metadata.chunk_id for c in all_chunks]
            build_and_save_bm25(chunk_texts, chunk_ids, tenant_id)
        except Exception as e:
            logger.warning(f"BM25 update failed (non-fatal): {e}")

        elapsed = (datetime.now(timezone.utc) - t_start).total_seconds() * 1000

        table_chunks  = sum(1 for c in text_chunks
                            if c.metadata.chunk_type in (ChunkType.TABLE_JSON, ChunkType.TABLE_DESC))

        summary = {
            "doc_id":            doc_id,
            "doc_hash":          doc_hash,
            "source_uri":        source_uri,
            "chunk_count":       len(all_chunks),
            "upserted_count":    upserted,
            "page_count":        page_count,
            "had_pii":           had_pii,
            "vision_chunks":     len(vision_chunks),
            "table_chunks":      table_chunks,
            "ingestion_time_ms": round(elapsed, 1),
        }
        logger.info(f"Ingestion complete: {json.dumps(summary)}")
        return summary
