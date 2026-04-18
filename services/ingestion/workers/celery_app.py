"""
Celery async ingestion worker.

WHY ASYNC:
  Ingestion of a 50-page PDF takes 30-90 seconds:
    - Docling parsing: 10-20s
    - GPT-4o Vision calls: 5-30s (concurrent, rate-limited)
    - Batch embedding: 1-5s
    - Pinecone upsert: 2-10s
  HTTP requests cannot wait this long (timeout risk, bad UX).
  Solution: POST /ingest -> returns job_id immediately -> Celery does the work.
  GET /ingest/status/{doc_id} -> polls until done.

JOB STATUS in Redis:
  Key: ingestion:status:{doc_id}
  Value: {"status": "pending|processing|complete|failed", "doc_id": ..., "error": ...}
  TTL: 7 days

DEAD LETTER QUEUE:
  After max_retries exhausted, push to Redis list: dlq:ingestion:failed
  Contains: tenant_id, doc_id, error, timestamp for debugging and reprocessing.

GRACEFUL SHUTDOWN:
  Celery workers drain in-flight tasks before stopping.
  Never interrupt an embedding batch mid-call.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone

import redis as redis_lib
from celery import Celery
from celery.signals import worker_shutdown

from core.config import get_settings

settings = get_settings()
logger   = logging.getLogger(__name__)

celery = Celery(
    "ingestion",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    worker_prefetch_multiplier=1,    # One ingestion at a time per worker
    task_soft_time_limit=600,        # 10 min soft limit
    task_time_limit=720,             # 12 min hard limit
    task_default_rate_limit="10/m",  # 10 ingestions per minute per worker
    result_expires=86400,
    broker_connection_retry_on_startup=True,
)

_redis = redis_lib.Redis.from_url(settings.redis_url, decode_responses=True)

STATUS_KEY_PREFIX = "ingestion:status"
DLQ_KEY           = "dlq:ingestion:failed"
STATUS_TTL        = 7 * 24 * 3600   # 7 days


def _status_key(doc_id: str) -> str:
    return f"{STATUS_KEY_PREFIX}:{doc_id}"


def set_status(doc_id: str, tenant_id: str, status: str, extra: dict = None):
    """Write ingestion status to Redis."""
    data = {
        "status":     status,
        "doc_id":     doc_id,
        "tenant_id":  tenant_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        data.update(extra)
    _redis.set(_status_key(doc_id), json.dumps(data), ex=STATUS_TTL)


def get_status(doc_id: str) -> dict | None:
    """Read ingestion status from Redis."""
    raw = _redis.get(_status_key(doc_id))
    return json.loads(raw) if raw else None


def push_to_dlq(tenant_id: str, doc_id: str, error: str, retries: int):
    """Push failed job to dead letter queue for debugging."""
    _redis.lpush(DLQ_KEY, json.dumps({
        "tenant_id":  tenant_id,
        "doc_id":     doc_id,
        "error":      error[:500],
        "retry_count": retries,
        "failed_at":  datetime.now(timezone.utc).isoformat(),
    }))
    _redis.ltrim(DLQ_KEY, 0, 999)   # Keep last 1000 failures


@celery.task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    name="ingest_document",
    queue="ingestion",
)
def ingest_document_task(
    self,
    file_bytes_b64: str,       # base64-encoded bytes (Celery can't handle raw bytes)
    original_filename: str,
    tenant_id: str,
    doc_id: str,
    language: str = "en",
):
    """
    Celery task: run the full ingestion pipeline for one document.

    Parameters are JSON-serialisable (Celery requirement).
    file_bytes are base64-encoded in the task payload.
    """
    import base64
    from pipeline.orchestrator import IngestionOrchestrator
    from core.exceptions import DuplicateDocumentError, ParseFailedError

    set_status(doc_id, tenant_id, "processing")

    try:
        file_bytes = base64.b64decode(file_bytes_b64)
        orchestrator = IngestionOrchestrator()

        # Run async orchestrator in a new event loop (Celery is sync)
        loop    = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            summary = loop.run_until_complete(
                orchestrator.ingest(
                    file_bytes=file_bytes,
                    original_filename=original_filename,
                    tenant_id=tenant_id,
                    doc_id=doc_id,
                    language=language,
                )
            )
        finally:
            loop.close()

        set_status(doc_id, tenant_id, "complete", {"summary": summary})
        return summary

    except DuplicateDocumentError as e:
        # Idempotency: not an error — just report it
        set_status(doc_id, tenant_id, "duplicate", {"existing_doc_id": e.existing_doc_id})
        return {"status": "duplicate", "doc_id": doc_id}

    except ParseFailedError as e:
        # Parse failures are unrecoverable — don't retry
        error_msg = str(e)
        set_status(doc_id, tenant_id, "failed", {"error": error_msg})
        push_to_dlq(tenant_id, doc_id, error_msg, self.request.retries)
        raise   # Celery marks task as FAILURE

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Ingestion task failed: {error_msg}", exc_info=True)

        try:
            # Retry with backoff for transient errors
            raise self.retry(
                exc=e,
                countdown=30 * (2 ** self.request.retries),
            )
        except self.MaxRetriesExceededError:
            set_status(doc_id, tenant_id, "failed", {"error": error_msg})
            push_to_dlq(tenant_id, doc_id, error_msg, self.request.retries)
            raise
