"""
Upload router — POST /ingest and GET /ingest/status/{doc_id}

POST /ingest:
  - Accepts multipart file upload
  - Validates file immediately (sync) → 400 on bad file
  - Enqueues Celery task → returns 202 with doc_id + job status URL
  - Never blocks for more than ~200ms

GET /ingest/status/{doc_id}:
  - Polls Redis for job status
  - Returns: pending | processing | complete | failed | duplicate
"""
import base64
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from pipeline.file_validator import validate_upload
from workers.celery_app import ingest_document_task, get_status
from core.exceptions import DocumentTooLargeError, UnsupportedFileTypeError

router = APIRouter()


class IngestResponse(BaseModel):
    doc_id:     str
    status:     str             # "queued"
    status_url: str
    message:    str


class StatusResponse(BaseModel):
    doc_id:    str
    status:    str              # pending|processing|complete|failed|duplicate
    summary:   dict | None = None
    error:     str | None = None


@router.post("/ingest", response_model=IngestResponse, status_code=202)
async def ingest_document(
    file:      UploadFile = File(...),
    tenant_id: str        = Form(...),
    language:  str        = Form("en"),
    doc_id:    str | None = Form(None),
):
    """
    Upload a document for ingestion into the RAG pipeline.

    Returns immediately with a doc_id. Poll GET /ingest/status/{doc_id}
    to track progress. Processing typically takes 30-120 seconds depending
    on document size and number of charts.

    Supported formats: PDF, DOCX, PPTX, XLSX, TXT, MD, CSV
    Max size: 50MB (configurable)
    Max pages: 500
    """
    file_bytes = await file.read()
    filename   = file.filename or "upload"

    # Validate synchronously before queueing
    try:
        validation = validate_upload(file_bytes, filename, tenant_id)
    except DocumentTooLargeError as e:
        raise HTTPException(400, detail=f"File too large: {e}")
    except UnsupportedFileTypeError as e:
        raise HTTPException(415, detail=f"Unsupported file type: {e.mime_type}. "
                                        f"Supported: PDF, DOCX, PPTX, XLSX, TXT, MD")
    except ValueError as e:
        raise HTTPException(400, detail=str(e))

    final_doc_id = doc_id or str(uuid4())

    # Encode bytes for Celery (JSON-safe)
    encoded = base64.b64encode(file_bytes).decode("utf-8")

    # Enqueue async task
    ingest_document_task.apply_async(
        args=[encoded, validation["safe_filename"], tenant_id, final_doc_id, language],
        task_id=final_doc_id,
        queue="ingestion",
    )

    return IngestResponse(
        doc_id=final_doc_id,
        status="queued",
        status_url=f"/api/v1/ingest/status/{final_doc_id}",
        message=f"Document '{validation['safe_filename']}' queued for ingestion. "
                f"Poll status_url for progress.",
    )


@router.get("/ingest/status/{doc_id}", response_model=StatusResponse)
async def get_ingestion_status(doc_id: str):
    """
    Poll ingestion job status.
    Status values: pending | processing | complete | failed | duplicate
    """
    status_data = get_status(doc_id)
    if not status_data:
        raise HTTPException(404, detail=f"No ingestion job found for doc_id: {doc_id}")

    return StatusResponse(
        doc_id=doc_id,
        status=status_data.get("status", "unknown"),
        summary=status_data.get("summary"),
        error=status_data.get("error"),
    )
