"""
Layout Router — API endpoints for the layout engine.
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
import time

from ..services.layout.layout_engine import LayoutEngine, solve_slide_with_relaxation
from ..services.layout.font_cache import preload_all_fonts, get_cache_stats
from ..services.layout.relaxation import reconcile_slide_indices

router = APIRouter(prefix="/layout", tags=["layout"])


class SlideInput(BaseModel):
    slide_id: str
    slide_type: str
    slide_index: int = 0
    action_title: str = ""
    layout_hints: Dict = Field(default_factory=dict)
    content: Dict = Field(default_factory=dict)
    outline_context: Optional[Dict] = None


class LayoutElementOutput(BaseModel):
    x: int
    y: int
    width: int
    height: int
    font_size_px: int
    font_size_units: int
    z_index: int
    text_align: str


class LayoutSolutionOutput(BaseModel):
    slide_id: str
    relaxation_tier: int
    solve_time_ms: float
    warnings: List[str]
    elements: Dict[str, LayoutElementOutput]
    font_scale_override: Optional[float] = None


class SolveSlideRequest(BaseModel):
    slide: SlideInput
    theme: str = "modern_light"
    language: str = "en"
    canvas_px_w: int = 1280
    canvas_px_h: int = 720


class SolveDeckRequest(BaseModel):
    slides: List[SlideInput]
    theme: str = "modern_light"
    language: str = "en"
    canvas_px_w: int = 1280
    canvas_px_h: int = 720


class SolveResponse(BaseModel):
    success: bool
    solutions: List[LayoutSolutionOutput]


class TelemetryEvent(BaseModel):
    slideId: str
    solveTimeMs: float
    relaxationTier: int
    workerIndex: int
    queueDepth: int


class TelemetryBatchRequest(BaseModel):
    events: List[TelemetryEvent]


class HealthResponse(BaseModel):
    status: str
    fonts_loaded: int
    cache_stats: Dict


@router.post("/solve-slide", response_model=LayoutSolutionOutput)
async def solve_single_slide(request: SolveSlideRequest):
    """Solve layout for a single slide."""
    try:
        slide_dict = request.slide.dict()

        solution, _ = solve_slide_with_relaxation(
            slide=slide_dict,
            theme=request.theme,
            language=request.language,
            canvas_px_w=request.canvas_px_w,
            canvas_px_h=request.canvas_px_h,
        )

        elements = {
            elem_id: LayoutElementOutput(**elem)
            for elem_id, elem in solution.elements.items()
        }

        return LayoutSolutionOutput(
            slide_id=solution.slide_id,
            relaxation_tier=solution.relaxation_tier,
            solve_time_ms=solution.solve_time_ms,
            warnings=solution.warnings,
            elements=elements,
            font_scale_override=solution.font_scale_override,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Layout solve failed: {str(e)}"
        )


@router.post("/solve-deck", response_model=SolveResponse)
async def solve_full_deck(request: SolveDeckRequest):
    """Solve layouts for an entire deck."""
    try:
        engine = LayoutEngine()
        slides = [s.dict() for s in request.slides]

        solutions = engine.solve_deck(
            slides=slides,
            theme=request.theme,
            language=request.language,
            canvas_px_w=request.canvas_px_w,
            canvas_px_h=request.canvas_px_h,
        )

        outputs = []
        for solution in solutions:
            elements = {
                elem_id: LayoutElementOutput(**elem)
                for elem_id, elem in solution.elements.items()
            }
            outputs.append(LayoutSolutionOutput(
                slide_id=solution.slide_id,
                relaxation_tier=solution.relaxation_tier,
                solve_time_ms=solution.solve_time_ms,
                warnings=solution.warnings,
                elements=elements,
                font_scale_override=solution.font_scale_override,
            ))

        return SolveResponse(success=True, solutions=outputs)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Deck layout solve failed: {str(e)}"
        )


@router.post("/reconcile-indices")
async def reconcile_indices(slides: List[Dict]):
    """Reconcile slide indices after continuation slide creation."""
    return reconcile_slide_indices(slides)


@router.post("/telemetry")
async def receive_telemetry(batch: TelemetryBatchRequest):
    """Receive frontend telemetry events."""
    # Store or forward to Prometheus
    # Fire-and-forget: always return success
    return {"received": len(batch.events)}


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint for the layout engine."""
    try:
        stats = get_cache_stats()
        return HealthResponse(
            status="ok",
            fonts_loaded=stats.get("size", 0),
            cache_stats=stats,
        )
    except Exception as e:
        return HealthResponse(
            status="degraded",
            fonts_loaded=0,
            cache_stats={"error": str(e)},
        )


@router.post("/preload-fonts")
async def preload_fonts():
    """Preload all theme fonts."""
    try:
        preload_all_fonts()
        return {"status": "fonts_preloaded"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Font preload failed: {str(e)}"
        )