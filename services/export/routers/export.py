"""
Export API router.

POST /api/v1/export
  Accepts full deck JSON + LayoutSolutions.
  Returns signed S3 URL + metadata.
  HTTP 422: validation errors (deck has blocking_errors or bad chart data).
  HTTP 500: unexpected server error.

GET /api/v1/export/health
  Lightweight health check for load balancers.
"""
from __future__ import annotations
import time
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Any, Dict

from engine.renderer import PresentationRenderer
from storage.s3_client import upload_pptx, generate_signed_url
from core.exceptions import ExportValidationError
from core.config import get_settings

router   = APIRouter()
logger   = logging.getLogger(__name__)
settings = get_settings()
renderer = PresentationRenderer()


class ExportRequest(BaseModel):
    presentation_id:  str
    schema_version:   str           = "1.0.0"
    aspect_ratio:     str           = "16:9"
    deck:             Dict[str, Any]           # Full Phase 1 deck JSON
    layout_solutions: Dict[str, Any]           # {slide_id: LayoutSolution} from Phase 2
    plan_tier:        str           = Field(default="free", pattern="^(free|pro|enterprise)$")


class ExportResponse(BaseModel):
    presentation_id:  str
    download_url:     str
    expires_in_seconds: int
    slide_count:      int
    file_size_bytes:  int
    export_time_ms:   float
    has_export_errors: bool = False  # True if any slides used error placeholder


@router.post("/export", response_model=ExportResponse)
async def export_presentation(request: ExportRequest):
    """
    Convert a presentation deck + LayoutSolutions to a native PPTX file.

    The caller is responsible for fetching the LayoutSolutions from Phase 2
    (POST /api/v1/layout/solve-deck) before calling this endpoint.

    Error responses
    ---------------
    HTTP 422: deck has blocking_errors, invalid chart values, or schema violations.
              The detail.blocking_errors field lists every specific problem.
    HTTP 500: unexpected server error — check export service logs.
    """
    start_time = time.perf_counter()

    try:
        pptx_bytes = renderer.render(
            deck=request.deck,
            layout_solutions=request.layout_solutions,
            plan_tier=request.plan_tier,
        )

        deck_title = request.deck.get("metadata", {}).get("title", "presentation")
        s3_key     = upload_pptx(request.presentation_id, pptx_bytes, deck_title)
        url        = generate_signed_url(s3_key, request.plan_tier)

        expiry_map = {
            "free":       settings.url_expiry_free,
            "pro":        settings.url_expiry_pro,
            "enterprise": settings.url_expiry_enterprise,
        }
        expiry_sec  = expiry_map.get(request.plan_tier, settings.url_expiry_free)
        export_ms   = (time.perf_counter() - start_time) * 1000
        slide_count = len(request.deck.get("slides", []))

        logger.info(
            "export_complete",
            presentation_id=request.presentation_id,
            slide_count=slide_count,
            file_size_bytes=len(pptx_bytes),
            export_time_ms=round(export_ms, 1),
        )

        return ExportResponse(
            presentation_id=request.presentation_id,
            download_url=url,
            expires_in_seconds=expiry_sec,
            slide_count=slide_count,
            file_size_bytes=len(pptx_bytes),
            export_time_ms=round(export_ms, 1),
        )

    except ExportValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error":           "export_validation_failed",
                "blocking_errors": exc.errors,
                "message":         (
                    "Export blocked due to validation errors. "
                    "Fix the listed blocking_errors and retry."
                ),
            },
        )

    except Exception as exc:
        logger.error(
            "export_failed_unexpected",
            presentation_id=request.presentation_id,
            error=str(exc),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Export failed: {str(exc)[:300]}",
        )


@router.get("/export/health")
async def export_health():
    return {"status": "ok", "service": "export"}
