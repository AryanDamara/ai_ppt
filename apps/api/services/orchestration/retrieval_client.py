"""
Retrieval client for Phase 1 Step 3 content generation.

Called from step3_content.py when the generation request includes doc_ids.
Makes a POST /search call to the ingestion service and returns
the context_string + citations for injection into the GPT-4o prompt.
"""
from __future__ import annotations
import logging

import httpx
from tenacity import retry, stop_after_attempt, wait_fixed

logger = logging.getLogger(__name__)

INGESTION_SERVICE_URL = "http://ingestion-service:8002"
SEARCH_TIMEOUT_SECONDS = 15.0


@retry(stop=stop_after_attempt(2), wait=wait_fixed(1), reraise=True)
async def retrieve_context(
    query:     str,
    tenant_id: str,
    doc_ids:   list[str] | None = None,
    top_k:     int | None       = None,
) -> dict:
    """
    Call the ingestion service to retrieve context for a slide topic.

    Parameters
    ----------
    query : the slide topic or action_title (used as retrieval query)
    tenant_id : authenticated tenant
    doc_ids : list of document IDs to restrict search to (from deck generation request)
    top_k : number of chunks to include in context (default from config)

    Returns
    -------
    dict with: context_string, citations, total_tokens, chunks_found, chunks_included

    If the ingestion service is unavailable or returns an error,
    logs a warning and returns empty context (graceful degradation —
    the slide will still be generated, just without grounding).
    """
    try:
        async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{INGESTION_SERVICE_URL}/api/v1/search",
                json={
                    "query":     query,
                    "tenant_id": tenant_id,
                    "doc_ids":   doc_ids,
                    "top_k":     top_k,
                },
            )
            resp.raise_for_status()
            return resp.json()

    except httpx.TimeoutException:
        logger.warning(
            f"Retrieval service timeout for query '{query[:40]}'. "
            f"Falling back to parametric generation."
        )
        return {"context_string": "", "citations": [], "total_tokens": 0,
                "chunks_found": 0, "chunks_included": 0}

    except Exception as e:
        logger.error(f"Retrieval failed: {e}. Falling back to parametric.")
        return {"context_string": "", "citations": [], "total_tokens": 0,
                "chunks_found": 0, "chunks_included": 0}
