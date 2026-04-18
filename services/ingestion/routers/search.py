"""
Search router — POST /search (called by Phase 1 Step 3).

This endpoint is the Phase 1 ↔ Phase 4 interface.
Phase 1 Step 3 calls this when generating content for a slide that has
doc_ids attached (user selected documents to ground this deck in).

Request: {query, tenant_id, doc_ids, top_k}
Response: {context_string, citations, total_tokens, chunks_found}
"""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from retrieval.hybrid_searcher import HybridSearcher
from retrieval.reranker import CrossEncoderReranker
from retrieval.context_packer import ContextPacker
from core.exceptions import RetrievalError

router   = APIRouter()
logger   = logging.getLogger(__name__)

_searcher = HybridSearcher()
_reranker = CrossEncoderReranker()
_packer   = ContextPacker()


class SearchRequest(BaseModel):
    query:     str
    tenant_id: str
    doc_ids:   list[str] | None = None   # None = search all tenant docs
    top_k:     int | None       = None   # Final chunks to include in context


class SearchResponse(BaseModel):
    context_string: str           # Inject into Phase 1 Step 3 prompt
    citations:      list[dict]    # For slide.citations[] in Phase 1 schema
    total_tokens:   int
    chunks_found:   int
    chunks_included: int


@router.post("/search", response_model=SearchResponse)
async def search_documents(req: SearchRequest):
    """
    Hybrid search + rerank + context pack for slide generation.

    Called by apps/api/services/orchestration/retrieval_client.py
    during Phase 1 Step 3 content generation.

    The context_string is ready to inject directly into the GPT-4o prompt.
    """
    if not req.query or not req.query.strip():
        raise HTTPException(400, "Query cannot be empty")
    if not req.tenant_id:
        raise HTTPException(400, "tenant_id is required")

    try:
        # Hybrid search
        candidates = await _searcher.search(
            query=req.query,
            tenant_id=req.tenant_id,
            doc_ids_filter=req.doc_ids,
        )

        if not candidates:
            return SearchResponse(
                context_string="",
                citations=[],
                total_tokens=0,
                chunks_found=0,
                chunks_included=0,
            )

        # Rerank
        reranked = await _reranker.rerank(
            query=req.query,
            chunks=candidates,
            top_k=req.top_k,
        )

        # Pack context
        packed = _packer.pack(chunks=reranked, query=req.query)
        citations = _packer.build_citation_list(packed["citation_map"])

        return SearchResponse(
            context_string=packed["context_string"],
            citations=citations,
            total_tokens=packed["total_tokens"],
            chunks_found=len(candidates),
            chunks_included=packed["chunks_included"],
        )

    except Exception as e:
        logger.error(f"Search failed: {e}", exc_info=True)
        raise HTTPException(500, detail=f"Search failed: {str(e)[:200]}")
