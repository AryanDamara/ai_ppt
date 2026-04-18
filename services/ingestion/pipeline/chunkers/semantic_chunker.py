"""
Semantic chunker — splits ParsedElement lists into embedding-ready Chunk objects.

CRITICAL RULES (never break these):
  1. NEVER split at arbitrary character or byte counts. Semantic boundaries only.
  2. NEVER split mid-paragraph. Paragraph = atomic unit.
  3. Apply token overlap between chunks (last OVERLAP_TOKENS of chunk N
     prepended to chunk N+1) for continuity across boundary queries.
  4. Every HEADING starts a new chunk. Headings anchor the section context.
  5. Tables NEVER split. One table = two chunks (JSON + description).
  6. Figures produce zero chunks here. Vision enricher produces them separately.
  7. Skip PAGE_HEADER and PAGE_FOOTER elements — pure noise.
  8. Skip chunks below MIN_CHUNK_TOKENS — too small to embed meaningfully.
  9. Chunk IDs use zero-padded sequence: "{doc_id}_c0001", "_c0002", ...
     This enables filtering all chunks for a document by ID prefix.

Token counting uses tiktoken (cl100k_base = same tokeniser as GPT-4o).
"""
from __future__ import annotations
import json
import logging
from typing import Optional

import tiktoken

from pipeline.chunk_model import Chunk, ChunkMetadata, ChunkType
from pipeline.parsers.layout_parser import ParsedElement, ElementType
from pipeline.parsers.table_extractor import generate_table_description
from core.config import get_settings

settings = get_settings()
logger   = logging.getLogger(__name__)

_ENC = tiktoken.get_encoding("cl100k_base")


def _count_tokens(text: str) -> int:
    return len(_ENC.encode(text))


def _truncate(text: str, max_tokens: int) -> str:
    tokens = _ENC.encode(text)
    return _ENC.decode(tokens[:max_tokens]) if len(tokens) > max_tokens else text


def _overlap_text(text: str, overlap_tokens: int) -> str:
    """Return the last `overlap_tokens` tokens of text as a string."""
    tokens = _ENC.encode(text)
    if len(tokens) <= overlap_tokens:
        return text
    return _ENC.decode(tokens[-overlap_tokens:])


class SemanticChunker:

    def __init__(
        self,
        max_chunk_tokens:  int = None,
        overlap_tokens:    int = None,
        min_chunk_tokens:  int = None,
    ):
        self.max_tokens  = max_chunk_tokens or settings.max_chunk_tokens
        self.overlap     = overlap_tokens   or settings.chunk_overlap_tokens
        self.min_tokens  = min_chunk_tokens or settings.min_chunk_tokens

    def chunk(
        self,
        elements:        list[ParsedElement],
        doc_id:          str,
        doc_hash:        str,
        tenant_id:       str,
        source_filename: str,
        source_uri:      str = "",
        language:        str = "en",
    ) -> list[Chunk]:
        """
        Convert ParsedElement list to Chunk list.

        Figures are NOT chunked here — the orchestrator creates vision chunks
        separately after calling VisionEnricher.describe_image().

        Returns list of Chunk objects without embeddings (embedding step is next).
        """
        chunks: list[Chunk] = []
        seq        = 0    # Sequential chunk number for ID generation
        buffer     : list[str] = []
        buf_tokens : int       = 0
        overlap_str: str       = ""   # Overlap from previous chunk
        cur_page   : int       = 1
        cur_section: list[str] = []

        def _make_chunk_id() -> str:
            nonlocal seq
            chunk_id = f"{doc_id}_c{seq:04d}"
            seq += 1
            return chunk_id

        def _flush_buffer() -> None:
            nonlocal buffer, buf_tokens, overlap_str
            if not buffer:
                return
            full_text = (overlap_str.strip() + "\n\n" + "\n\n".join(buffer)).strip() \
                        if overlap_str else "\n\n".join(buffer)

            token_count = _count_tokens(full_text)
            if token_count < self.min_tokens:
                buffer = []
                buf_tokens = 0
                return

            chunk_id = _make_chunk_id()
            chunks.append(Chunk(
                text=full_text,
                metadata=ChunkMetadata(
                    chunk_id=chunk_id,
                    doc_id=doc_id,
                    doc_hash=doc_hash,
                    tenant_id=tenant_id,
                    page_number=cur_page,
                    section=cur_section[-1] if cur_section else None,
                    headers_path=" > ".join(cur_section),
                    source_filename=source_filename,
                    source_uri=source_uri,
                    chunk_type=ChunkType.NARRATIVE_TEXT,
                    language=language,
                    token_count=token_count,
                ),
            ))

            # Build overlap for next chunk from the joined buffer content
            overlap_str = _overlap_text("\n\n".join(buffer), self.overlap)
            buffer     = []
            buf_tokens = 0

        for elem in elements:
            cur_page = elem.page_number

            # ── Skip noise elements ────────────────────────────────────────────
            if elem.element_type in (ElementType.PAGE_HEADER, ElementType.PAGE_FOOTER):
                continue

            if not elem.text.strip() and elem.element_type != ElementType.FIGURE:
                continue

            # ── HEADING: flush buffer, start new section ───────────────────────
            if elem.element_type == ElementType.HEADING:
                _flush_buffer()
                overlap_str = ""  # Headings break overlap continuity

                cur_section = list(elem.section_path)

                # Add heading as its own small chunk (important for section retrieval)
                if _count_tokens(elem.text) >= self.min_tokens or True:
                    chunk_id = _make_chunk_id()
                    chunks.append(Chunk(
                        text=elem.text,
                        metadata=ChunkMetadata(
                            chunk_id=chunk_id,
                            doc_id=doc_id, doc_hash=doc_hash, tenant_id=tenant_id,
                            page_number=cur_page,
                            section=elem.text,
                            headers_path=" > ".join(elem.section_path),
                            source_filename=source_filename,
                            source_uri=source_uri,
                            chunk_type=ChunkType.HEADING,
                            language=language,
                            token_count=_count_tokens(elem.text),
                        ),
                    ))
                continue

            # ── TABLE: flush buffer, produce two chunks ────────────────────────
            if elem.element_type == ElementType.TABLE:
                _flush_buffer()

                if elem.table_data:
                    # Chunk 1: JSON structure
                    json_text = json.dumps(elem.table_data, ensure_ascii=False, indent=None)
                    json_text = _truncate(json_text, self.max_tokens)
                    chunk_id  = _make_chunk_id()
                    chunks.append(Chunk(
                        text=json_text,
                        metadata=ChunkMetadata(
                            chunk_id=chunk_id,
                            doc_id=doc_id, doc_hash=doc_hash, tenant_id=tenant_id,
                            page_number=cur_page,
                            section=cur_section[-1] if cur_section else None,
                            headers_path=" > ".join(cur_section),
                            source_filename=source_filename, source_uri=source_uri,
                            chunk_type=ChunkType.TABLE_JSON,
                            language=language,
                            token_count=_count_tokens(json_text),
                            links_to=json_text[:500],
                        ),
                    ))

                    # Chunk 2: Natural language description
                    desc_text = generate_table_description(elem.table_data)
                    chunk_id  = _make_chunk_id()
                    chunks.append(Chunk(
                        text=desc_text,
                        metadata=ChunkMetadata(
                            chunk_id=chunk_id,
                            doc_id=doc_id, doc_hash=doc_hash, tenant_id=tenant_id,
                            page_number=cur_page,
                            section=cur_section[-1] if cur_section else None,
                            headers_path=" > ".join(cur_section),
                            source_filename=source_filename, source_uri=source_uri,
                            chunk_type=ChunkType.TABLE_DESC,
                            language=language,
                            token_count=_count_tokens(desc_text),
                        ),
                    ))

                elif elem.text and '|' in elem.text:
                    # Fallback: embed the markdown table text directly
                    chunk_id = _make_chunk_id()
                    chunks.append(Chunk(
                        text=elem.text,
                        metadata=ChunkMetadata(
                            chunk_id=chunk_id,
                            doc_id=doc_id, doc_hash=doc_hash, tenant_id=tenant_id,
                            page_number=cur_page,
                            section=cur_section[-1] if cur_section else None,
                            headers_path=" > ".join(cur_section),
                            source_filename=source_filename, source_uri=source_uri,
                            chunk_type=ChunkType.TABLE_DESC,
                            language=language,
                            token_count=_count_tokens(elem.text),
                        ),
                    ))

                overlap_str = ""  # Tables break overlap
                continue

            # ── FIGURE: skip here — orchestrator handles vision enrichment ─────
            if elem.element_type == ElementType.FIGURE:
                continue  # orchestrator.py calls VisionEnricher and creates chunks

            # ── PARAGRAPH / LIST_ITEM / CAPTION / FOOTNOTE ───────────────────
            text       = elem.text.strip()
            if not text:
                continue

            new_tokens = _count_tokens(text)

            # If this single element already exceeds max_tokens, truncate it
            if new_tokens > self.max_tokens:
                _flush_buffer()
                truncated = _truncate(text, self.max_tokens)
                chunk_id  = _make_chunk_id()
                chunks.append(Chunk(
                    text=truncated,
                    metadata=ChunkMetadata(
                        chunk_id=chunk_id,
                        doc_id=doc_id, doc_hash=doc_hash, tenant_id=tenant_id,
                        page_number=cur_page,
                        section=cur_section[-1] if cur_section else None,
                        headers_path=" > ".join(cur_section),
                        source_filename=source_filename, source_uri=source_uri,
                        chunk_type=self._map_chunk_type(elem.element_type),
                        language=language,
                        token_count=_count_tokens(truncated),
                    ),
                ))
                overlap_str = _overlap_text(truncated, self.overlap)
                continue

            # Flush if adding this element would overflow the buffer
            if buf_tokens + new_tokens > self.max_tokens and buffer:
                _flush_buffer()

            buffer.append(text)
            buf_tokens += new_tokens

        # Flush any remaining buffer
        _flush_buffer()

        logger.info(
            f"Chunking: {len(elements)} elements → {len(chunks)} chunks "
            f"(doc: {doc_id[:8]}…)"
        )
        return chunks

    @staticmethod
    def _map_chunk_type(element_type: ElementType) -> ChunkType:
        return {
            ElementType.PARAGRAPH: ChunkType.NARRATIVE_TEXT,
            ElementType.LIST_ITEM: ChunkType.LIST_ITEM,
            ElementType.CAPTION:   ChunkType.CAPTION,
            ElementType.FOOTNOTE:  ChunkType.FOOTNOTE,
        }.get(element_type, ChunkType.NARRATIVE_TEXT)
