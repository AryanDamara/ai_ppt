"""
Document management endpoints for the Phase 1 API.

These endpoints proxy to the ingestion service and provide a unified API
surface for the frontend to manage documents (upload, list, delete)
without needing to know about the ingestion service directly.

Endpoints:
  POST   /api/v1/documents/upload    → Proxy to ingestion /ingest
  GET    /api/v1/documents           → List tenant documents
  GET    /api/v1/documents/{doc_id}  → Get document status
  DELETE /api/v1/documents/{doc_id}  → Delete document (GDPR)
"""
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

INGESTION_SERVICE_URL = "http://ingestion-service:8002"


class DocumentUploadResponse(BaseModel):
    doc_id: str
    status: str
    status_url: str
    message: str


class DocumentStatusResponse(BaseModel):
    doc_id: str
    status: str
    summary: dict | None = None
    error: str | None = None


class DocumentListResponse(BaseModel):
    documents: list[dict]
    total: int


@router.post("/documents/upload", response_model=DocumentUploadResponse, status_code=202)
async def upload_document(
    file: UploadFile = File(...),
    tenant_id: str = Form(...),
    language: str = Form("en"),
    doc_id: Optional[str] = Form(None),
):
    """
    Upload a document for RAG ingestion.

    Proxies the file to the ingestion service and returns a doc_id
    for tracking ingestion progress. The frontend should poll
    GET /documents/{doc_id} for status updates.

    Supported formats: PDF, DOCX, PPTX, XLSX, TXT, MD, CSV
    Max size: 50MB
    """
    file_bytes = await file.read()

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Forward as multipart form data to ingestion service
            files = {"file": (file.filename or "upload", file_bytes, file.content_type or "application/octet-stream")}
            data = {"tenant_id": tenant_id, "language": language}
            if doc_id:
                data["doc_id"] = doc_id

            resp = await client.post(
                f"{INGESTION_SERVICE_URL}/api/v1/ingest",
                files=files,
                data=data,
            )

            if resp.status_code == 202:
                result = resp.json()
                return DocumentUploadResponse(
                    doc_id=result["doc_id"],
                    status=result["status"],
                    status_url=f"/api/v1/documents/{result['doc_id']}",
                    message=result.get("message", "Document queued for ingestion."),
                )
            elif resp.status_code == 400:
                raise HTTPException(400, detail=resp.json().get("detail", "Invalid file"))
            elif resp.status_code == 415:
                raise HTTPException(415, detail=resp.json().get("detail", "Unsupported file type"))
            else:
                raise HTTPException(
                    resp.status_code,
                    detail=f"Ingestion service error: {resp.text[:200]}",
                )

    except httpx.TimeoutException:
        raise HTTPException(504, detail="Ingestion service timeout. Please try again.")
    except httpx.ConnectError:
        raise HTTPException(503, detail="Ingestion service unavailable. Please try again later.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Document upload proxy failed: {e}")
        raise HTTPException(500, detail=f"Upload failed: {str(e)[:200]}")


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(tenant_id: str):
    """
    List all documents ingested for a tenant.
    Proxies to the ingestion service.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{INGESTION_SERVICE_URL}/api/v1/documents",
                params={"tenant_id": tenant_id},
            )
            resp.raise_for_status()
            data = resp.json()
            return DocumentListResponse(
                documents=data.get("documents", []),
                total=data.get("total", 0),
            )
    except httpx.ConnectError:
        # Graceful degradation: return empty list if ingestion service is down
        logger.warning("Ingestion service unavailable for document listing")
        return DocumentListResponse(documents=[], total=0)
    except Exception as e:
        logger.error(f"Document listing failed: {e}")
        return DocumentListResponse(documents=[], total=0)


@router.get("/documents/{doc_id}", response_model=DocumentStatusResponse)
async def get_document_status(doc_id: str, tenant_id: str):
    """
    Get document ingestion status.
    Used for polling after upload to track ingestion progress.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{INGESTION_SERVICE_URL}/api/v1/ingest/status/{doc_id}",
            )
            if resp.status_code == 404:
                raise HTTPException(404, detail=f"Document {doc_id} not found")
            resp.raise_for_status()
            data = resp.json()
            return DocumentStatusResponse(
                doc_id=data["doc_id"],
                status=data["status"],
                summary=data.get("summary"),
                error=data.get("error"),
            )
    except HTTPException:
        raise
    except httpx.ConnectError:
        raise HTTPException(503, detail="Ingestion service unavailable")
    except Exception as e:
        logger.error(f"Document status check failed: {e}")
        raise HTTPException(500, detail=f"Status check failed: {str(e)[:200]}")


@router.delete("/documents/{doc_id}", status_code=204)
async def delete_document(doc_id: str, tenant_id: str):
    """
    Delete a document and all its vectors (GDPR right-to-erasure).
    Proxies to the ingestion service which handles Pinecone + Redis cleanup.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.delete(
                f"{INGESTION_SERVICE_URL}/api/v1/documents/{doc_id}",
                params={"tenant_id": tenant_id},
            )
            if resp.status_code == 404:
                raise HTTPException(404, detail=f"Document {doc_id} not found")
            if resp.status_code != 204:
                raise HTTPException(
                    resp.status_code,
                    detail=f"Deletion failed: {resp.text[:200]}",
                )
    except HTTPException:
        raise
    except httpx.ConnectError:
        raise HTTPException(503, detail="Ingestion service unavailable for deletion")
    except Exception as e:
        logger.error(f"Document deletion failed: {e}")
        raise HTTPException(500, detail=f"Deletion failed: {str(e)[:200]}")
