"""
Export integrations router — Google Slides export endpoint.

POST /api/v1/export/google-slides — export a completed deck to Google Slides
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from services.auth.jwt_validator import get_current_user, AuthenticatedUser
from core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


class GoogleSlidesExportRequest(BaseModel):
    presentation_id: str
    google_oauth_token: Optional[str] = None
    title_override:     Optional[str] = None


class GoogleSlidesExportResponse(BaseModel):
    slides_url:       str
    presentation_id:  str
    slide_count:      int
    status:           str


@router.post("/export/google-slides", response_model=GoogleSlidesExportResponse)
async def export_to_google_slides(
    body: GoogleSlidesExportRequest,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Export a completed deck to Google Slides.
    Requires the user to provide a Google OAuth token with Slides API scope.
    """
    # Fetch deck from database
    from services.db.session import get_db_session
    from services.db.models import Deck

    async with get_db_session() as session:
        record = await session.get(Deck, body.presentation_id)

    if not record:
        raise HTTPException(404, detail=f"Deck '{body.presentation_id}' not found")

    if record.generation_status not in ("complete", "partial_failure"):
        raise HTTPException(
            409,
            detail=f"Deck status is '{record.generation_status}'. Export requires 'complete'.",
        )

    deck_json = record.deck_json

    # Call Google Slides exporter
    try:
        from services.export_integrations.google_slides import GoogleSlidesExporter

        exporter = GoogleSlidesExporter(
            oauth_token=body.google_oauth_token or "",
        )

        result = await exporter.export_deck(
            deck_json=deck_json,
            title=body.title_override or deck_json.get("title", "AI Generated Presentation"),
        )

        logger.info(
            "google_slides_export_complete",
            presentation_id=body.presentation_id[:8],
            slides_url=result["slides_url"],
        )

        return GoogleSlidesExportResponse(
            slides_url=result["slides_url"],
            presentation_id=result["google_presentation_id"],
            slide_count=result["slide_count"],
            status="success",
        )

    except Exception as e:
        logger.error(f"Google Slides export failed: {e}")
        raise HTTPException(500, detail=f"Export failed: {str(e)}")
