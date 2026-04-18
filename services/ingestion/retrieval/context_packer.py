"""
Context packer — assembles retrieved chunks into a structured LLM prompt context.

OUTPUTS:
  1. context_string: formatted text injected into the Phase 1 Step 3 prompt.
     Contains [Source N] labels the LLM can reference in its output.
  2. citation_map: {source_label → RetrievedChunk} for building slide.citations[].
  3. total_tokens: so Phase 1 can track how much budget was consumed.

TOKEN BUDGET:
  max_tokens defaults to 4000 (leaving ~4000 for system prompt + output schema).
  The packer greedily adds chunks until the budget is exhausted.
  Higher-rerank-score chunks are added first (they are most relevant).

DEDUPLICATION:
  The same chunk_id may appear in multiple retrieval calls (e.g., if the deck has
  many slides on related topics). The packer deduplicates by chunk_id globally.

CITATION FORMAT:
  Chunks are labelled [Source 1], [Source 2], etc.
  The LLM prompt instructs: "When making specific factual claims, cite sources
  as [Source N]. Do not cite sources for general statements."
  The citation_map maps these labels back to chunk metadata for the slide JSON.
"""
from __future__ import annotations
import logging

import tiktoken

from pipeline.chunk_model import RetrievedChunk
from core.config import get_settings

settings = get_settings()
logger   = logging.getLogger(__name__)

_ENC               = tiktoken.get_encoding("cl100k_base")
MAX_CONTEXT_TOKENS = 4000   # Conservative — leaves room for system + schema


def _count_tokens(text: str) -> int:
    return len(_ENC.encode(text))


class ContextPacker:

    def pack(
        self,
        chunks:     list[RetrievedChunk],
        query:      str,
        max_tokens: int = MAX_CONTEXT_TOKENS,
    ) -> dict:
        """
        Pack chunks into context string with citation labels.

        Parameters
        ----------
        chunks : reranked chunks, sorted by rerank_score descending
        query : the original retrieval query (for logging)
        max_tokens : hard token budget for context block

        Returns
        -------
        dict with keys:
          context_string : str — inject into Phase 1 prompt
          citation_map   : dict[str, RetrievedChunk] — for slide.citations[]
          total_tokens   : int
          chunks_included : int
          chunks_excluded : int
        """
        if not chunks:
            return {
                "context_string": "",
                "citation_map":   {},
                "total_tokens":   0,
                "chunks_included": 0,
                "chunks_excluded": 0,
            }

        # Dedup by chunk_id
        seen_ids: set[str] = set()
        unique: list[RetrievedChunk] = []
        for c in chunks:
            if c.chunk_id not in seen_ids:
                seen_ids.add(c.chunk_id)
                unique.append(c)

        sections:    list[str]                   = []
        citation_map: dict[str, RetrievedChunk]  = {}
        total_tokens    = 0
        chunks_included = 0
        chunks_excluded = 0

        for idx, chunk in enumerate(unique):
            label = f"Source {idx + 1}"

            pg_info   = f"p.{chunk.page_number}" if chunk.page_number else "n.p."
            type_info = chunk.chunk_type.replace("_", " ").title()

            header = (
                f"[{label}] — {chunk.source_filename} ({pg_info}) | {type_info}\n"
                f"Relevance: {chunk.rerank_score:.2f}\n"
            )
            section       = f"{header}\n{chunk.text}\n"
            section_tokens = _count_tokens(section)

            if total_tokens + section_tokens > max_tokens:
                chunks_excluded += 1
                continue

            sections.append(section)
            citation_map[label] = chunk
            total_tokens       += section_tokens
            chunks_included    += 1

        divider        = "\n" + ("─" * 50) + "\n"
        context_string = divider.join(sections)

        logger.info(
            f"Context packed: {chunks_included}/{len(chunks)} chunks, "
            f"{total_tokens} tokens (query: '{query[:50]}')"
        )

        return {
            "context_string":   context_string,
            "citation_map":     citation_map,
            "total_tokens":     total_tokens,
            "chunks_included":  chunks_included,
            "chunks_excluded":  chunks_excluded,
        }

    def build_citation_list(
        self,
        citation_map: dict[str, RetrievedChunk],
    ) -> list[dict]:
        """
        Build the citations[] array for Phase 1 slide JSON schema.
        All included sources are cited (not just those explicitly referenced
        in the LLM output — the context was ground truth, all sources are relevant).
        """
        citations = []
        seen: set[str] = set()
        for label, chunk in citation_map.items():
            if chunk.chunk_id not in seen:
                seen.add(chunk.chunk_id)
                citations.append(
                    chunk.to_citation_dict(confidence_score=chunk.rerank_score)
                )
        return citations
