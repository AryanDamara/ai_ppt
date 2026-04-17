from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional
import redis as sync_redis
import json
from uuid import uuid4
from slowapi import Limiter
from slowapi.util import get_remote_address

from core.config import get_settings
from core.security import sanitize_prompt, compute_client_fingerprint
from core.logging import get_logger
from services.cache.semantic_cache import check_cache
from workers.celery_app import generate_presentation_task

settings = get_settings()
logger = get_logger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()
redis = sync_redis.Redis.from_url(settings.redis_url, decode_responses=True)

VALID_THEMES = [
    "corporate_dark", "modern_light", "startup_minimal",
    "healthcare_clinical", "financial_formal"
]

VALID_VERTICALS = [
    "general", "healthcare", "financial_services",
    "government", "technology", "legal"
]

VALID_FRAMEWORKS = [
    "pyramid_principle", "hero_journey", "chronological",
    "problem_solution", "compare_contrast"
]


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=10, max_length=2000)
    theme: str = Field(default="modern_light")
    narrative_framework: Optional[str] = Field(default=None)
    industry_vertical: Optional[str] = Field(default="general")
    language: Optional[str] = Field(default="en-US")
    audience: Optional[str] = Field(default=None)
    client_request_id: Optional[str] = Field(
        default=None,
        description="UUID for idempotency. Same ID = same job returned without re-running."
    )


class GenerateResponse(BaseModel):
    job_id: str
    status: str
    message: str
    cache_hit: bool = False
    idempotent: bool = False


@router.post("/generate", response_model=GenerateResponse)
@limiter.limit(f"{settings.rate_limit_per_minute}/minute")
async def generate_presentation(request: Request, body: GenerateRequest):
    """
    Submit a presentation generation request.
    Returns in under 200ms with a job_id.
    Client connects to /ws/job/{job_id} for real-time streaming.

    Idempotency: if client_request_id is provided and matches an existing job,
    the existing job_id is returned without triggering a new generation.

    Rate limit: {settings.rate_limit_per_minute} requests per minute per IP.
    """
    # ── Step 1: Sanitize input ────────────────────────────────────────────────
    body.prompt = sanitize_prompt(body.prompt)

    # ── Step 2: Validate enums ────────────────────────────────────────────────
    if body.theme not in VALID_THEMES:
        raise HTTPException(422, detail=f"Invalid theme. Must be one of: {VALID_THEMES}")

    if body.industry_vertical and body.industry_vertical not in VALID_VERTICALS:
        raise HTTPException(422, detail=f"Invalid industry_vertical. Must be one of: {VALID_VERTICALS}")

    if body.narrative_framework and body.narrative_framework not in VALID_FRAMEWORKS:
        raise HTTPException(422, detail=f"Invalid narrative_framework. Must be one of: {VALID_FRAMEWORKS}")

    # ── Step 3: Client-side Zod validation mirrored here ─────────────────────
    # (Pydantic handles this, but log if prompt was sanitized)
    fingerprint = compute_client_fingerprint(
        body.client_request_id, body.prompt, body.theme
    )

    # ── Step 4: Idempotency check ─────────────────────────────────────────────
    if body.client_request_id:
        # Check Redis for existing job with this client_request_id
        existing_job_id = redis.get(f"idempotency:{body.client_request_id}")
        if existing_job_id:
            existing_status = redis.hget(f"job:{existing_job_id}", "status") or "unknown"
            logger.info(
                "idempotency_hit",
                client_request_id=body.client_request_id,
                existing_job_id=existing_job_id,
            )
            return GenerateResponse(
                job_id=existing_job_id,
                status=existing_status,
                message="Returning existing job (idempotency key matched)",
                idempotent=True,
            )

    # ── Step 5: Semantic cache check ──────────────────────────────────────────
    try:
        cached = await check_cache(body.prompt, body.theme)
        if cached:
            cache_job_id = str(uuid4())
            redis.hset(f"job:{cache_job_id}", mapping={
                "status": "complete",
                "cached": "true",
                "deck_json": json.dumps(cached),
            })
            redis.expire(f"job:{cache_job_id}", 3600)
            logger.info("semantic_cache_hit", fingerprint=fingerprint)
            return GenerateResponse(
                job_id=cache_job_id,
                status="complete",
                message="Retrieved from semantic cache",
                cache_hit=True,
            )
    except Exception as e:
        # Cache read failure is non-fatal — continue to generation
        logger.warning("semantic_cache_read_failed", error=str(e))

    # ── Step 6: Dispatch to Celery ────────────────────────────────────────────
    # PRE-GENERATE the job_id and pass it explicitly to Celery as task_id.
    # This eliminates the race condition of needing the task ID before creation.
    job_id = str(uuid4())

    request_dict = body.model_dump()
    generate_presentation_task.apply_async(
        args=[job_id, request_dict],
        task_id=job_id,              # Force Celery to use our pre-generated UUID
    )

    # Store initial job state
    redis.hset(f"job:{job_id}", mapping={
        "status": "queued",
        "prompt_length": str(len(body.prompt)),  # Don't store full prompt in Redis
        "theme": body.theme,
        "fingerprint": fingerprint,
    })
    redis.expire(f"job:{job_id}", 7200)  # 2-hour TTL

    # Store idempotency mapping if client provided a request ID
    if body.client_request_id:
        redis.set(f"idempotency:{body.client_request_id}", job_id, ex=86400)

    logger.info(
        "generation_dispatched",
        job_id=job_id,
        theme=body.theme,
        industry=body.industry_vertical,
        prompt_length=len(body.prompt),
    )

    return GenerateResponse(
        job_id=job_id,
        status="queued",
        message="Generation started. Connect to WebSocket for real-time updates.",
    )


@router.get("/job/{job_id}")
async def get_job_status(job_id: str):
    """
    Polling fallback for clients that cannot maintain WebSocket connections.
    Also used to check status after page refresh.
    """
    job_data = redis.hgetall(f"job:{job_id}")

    if not job_data:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    response = {
        "job_id": job_id,
        "status": job_data.get("status", "unknown"),
    }

    if job_data.get("error"):
        response["error"] = job_data["error"]

    if job_data.get("cached") == "true" and job_data.get("deck_json"):
        response["deck"] = json.loads(job_data["deck_json"])

    return response


@router.delete("/cache")
async def invalidate_cache(pattern: str = ""):
    """
    Admin endpoint: manually invalidate cache entries.
    Used when a bad generation was cached and needs removal.
    pattern: substring to match against prompt_hash
    """
    from services.cache.semantic_cache import invalidate_cache as do_invalidate
    deleted = await do_invalidate(pattern)
    logger.info("cache_invalidated", pattern=pattern, deleted_count=deleted)
    return {"deleted": deleted}
