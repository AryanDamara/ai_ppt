"""
Feedback router — user feedback endpoints.

POST /api/v1/feedback       — submit thumbs up/down or edit feedback
GET  /api/v1/feedback/stats — get aggregated feedback statistics
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import Optional

from services.auth.jwt_validator import get_current_user, AuthenticatedUser
from services.llmops.feedback_collector import FeedbackCollector, FeedbackRecord
from core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

collector = FeedbackCollector()


class FeedbackRequest(BaseModel):
    deck_id:       str
    slide_id:      str
    feedback_type: str = Field(..., pattern="^(thumbs_up|thumbs_down|edit)$")
    edit_delta:    Optional[dict] = None
    original_value: Optional[str] = None
    new_value:     Optional[str] = None
    trace_id:      Optional[str] = None


class FeedbackResponse(BaseModel):
    feedback_id: str
    status:      str


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    body: FeedbackRequest,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Submit slide-level feedback (thumbs up/down or edit telemetry)."""
    record = FeedbackRecord(
        user_id=user.user_id,
        tenant_id=user.tenant_id,
        deck_id=body.deck_id,
        slide_id=body.slide_id,
        feedback_type=body.feedback_type,
        edit_delta=body.edit_delta,
        original_value=body.original_value,
        new_value=body.new_value,
        trace_id=body.trace_id,
    )

    feedback_id = await collector.record_feedback(record)
    logger.info(
        "feedback_received",
        feedback_type=body.feedback_type,
        deck_id=body.deck_id[:8],
        slide_id=body.slide_id[:8],
    )

    return FeedbackResponse(feedback_id=feedback_id, status="recorded")


@router.get("/feedback/stats")
async def get_feedback_stats(
    deck_id: Optional[str] = None,
    days: int = 30,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Get aggregated feedback statistics for the current tenant."""
    stats = await collector.get_feedback_stats(
        tenant_id=user.tenant_id,
        deck_id=deck_id,
        days=days,
    )
    return stats
