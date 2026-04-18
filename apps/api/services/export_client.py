"""
Export client — calls the Phase 3 export microservice from the Phase 1 backend.

Called from POST /api/v1/deck/{presentation_id}/export endpoint.
"""
from __future__ import annotations
import httpx
from core.config import get_settings

settings = get_settings()
EXPORT_SERVICE_URL = "http://export-service:8001"


async def trigger_pptx_export(
    deck:             dict,
    layout_solutions: dict,
    plan_tier:        str = "free",
) -> dict:
    """
    Call the export microservice and return the signed download URL + metadata.

    Parameters
    ----------
    deck : full deck JSON from Phase 1 (with Phase 2 font_scale written back)
    layout_solutions : {slide_id: LayoutSolution} from Phase 2 /layout/solve-deck
    plan_tier : "free" | "pro" | "enterprise"

    Returns
    -------
    dict with keys: download_url, expires_in_seconds, slide_count,
                    file_size_bytes, export_time_ms

    Raises
    ------
    ValueError : if the export service returns validation errors (HTTP 422)
    httpx.HTTPStatusError : for HTTP 5xx errors from the export service
    """
    async with httpx.AsyncClient(timeout=180.0) as client:  # 3-min timeout for large decks
        response = await client.post(
            f"{EXPORT_SERVICE_URL}/api/v1/export",
            json={
                "presentation_id": deck["presentation_id"],
                "schema_version":  deck.get("schema_version", "1.0.0"),
                "aspect_ratio":    deck.get("aspect_ratio", "16:9"),
                "deck":            deck,
                "layout_solutions": layout_solutions,
                "plan_tier":       plan_tier,
            },
        )

    if response.status_code == 422:
        error_data = response.json()
        raise ValueError(
            f"Export validation failed: {error_data.get('blocking_errors', [])}"
        )

    response.raise_for_status()
    return response.json()
