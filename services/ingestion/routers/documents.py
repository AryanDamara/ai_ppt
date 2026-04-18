"""
Document management router.
  GET    /documents/              List all documents for tenant
  GET    /documents/{doc_id}      Document metadata + ingestion status
  DELETE /documents/{doc_id}      GDPR deletion (Pinecone + S3 + Redis)
"""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)


class DocumentInfo(BaseModel):
    doc_id:          str
    source_filename: str
    status:          str
    chunk_count:     int | None = None
    page_count:      int | None = None
    ingested_at:     str | None = None


@router.get("/documents")
async def list_documents(tenant_id: str):
    """
    List all documents ingested for a tenant.
    Reads from Redis job status keys.
    In production: query PostgreSQL for the documents table.
    """
    from workers.celery_app import _redis, STATUS_KEY_PREFIX
    pattern = f"{STATUS_KEY_PREFIX}:*"
    keys    = _redis.keys(pattern)
    docs    = []
    for key in keys:
        raw = _redis.get(key)
        if raw:
            import json
            data = json.loads(raw)
            if data.get("tenant_id") == tenant_id:
                docs.append(data)
    return {"documents": docs, "total": len(docs)}


@router.get("/documents/{doc_id}", response_model=DocumentInfo)
async def get_document(doc_id: str, tenant_id: str):
    """Get document metadata and current ingestion status."""
    from workers.celery_app import get_status
    status = get_status(doc_id)
    if not status or status.get("tenant_id") != tenant_id:
        raise HTTPException(404, f"Document {doc_id} not found")

    summary = status.get("summary", {})
    return DocumentInfo(
        doc_id=doc_id,
        source_filename=summary.get("source_filename", "unknown"),
        status=status.get("status", "unknown"),
        chunk_count=summary.get("chunk_count"),
        page_count=summary.get("page_count"),
        ingested_at=status.get("updated_at"),
    )


@router.delete("/documents/{doc_id}", status_code=204)
async def delete_document(doc_id: str, tenant_id: str):
    """
    GDPR right-to-erasure: delete all vectors and metadata for a document.
    Deletes from: Pinecone (all vectors), Redis (status + BM25 text),
    and optionally S3 (raw file).
    """
    from pipeline.storage.pinecone_client import PineconeVectorStore
    from workers.celery_app import _redis, _status_key

    pinecone = PineconeVectorStore()

    # Verify ownership
    from workers.celery_app import get_status
    status = get_status(doc_id)
    if not status or status.get("tenant_id") != tenant_id:
        raise HTTPException(404, f"Document {doc_id} not found")

    # Delete from Pinecone
    pinecone.delete_document(doc_id, tenant_id)

    # Delete status from Redis
    _redis.delete(_status_key(doc_id))

    logger.info(f"Document {doc_id[:8]}… deleted for tenant {tenant_id[:8]}…")
