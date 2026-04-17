"""
Module 11 — Relaxation with Slide Re-Indexing
Continuation slide creation and index reconciliation.
"""

from dataclasses import dataclass
from typing import Optional, List, Dict
from uuid import uuid4


@dataclass
class RelaxationResult:
    solution: 'LayoutSolution'
    font_scale_to_write: Optional[float]
    layout_warnings_to_write: List[str]
    needs_continuation: bool = False
    continuation_bullets: List[dict] = None
    parent_section_id: str = None


def apply_relaxation_result(slide: dict, result: RelaxationResult) -> dict:
    """Apply relaxation results to slide JSON."""
    slide = dict(slide)

    if result.font_scale_to_write is not None:
        if "template" not in slide:
            slide["template"] = {}
        if "overrides" not in slide["template"]:
            slide["template"]["overrides"] = {}
        clamped = max(0.8, min(1.2, result.font_scale_to_write))
        slide["template"]["overrides"]["font_scale"] = clamped

    if result.layout_warnings_to_write:
        if "validation_state" not in slide:
            slide["validation_state"] = {"schema_compliant": True, "blocking_errors": [], "layout_warnings": []}
        slide["validation_state"]["layout_warnings"].extend(result.layout_warnings_to_write)

    return slide


def build_continuation_slide(original_slide: dict, overflow_bullets: List[dict]) -> dict:
    """Build a continuation slide for overflow content."""
    title = original_slide.get("action_title", "")
    if len(title) > 60:
        title = title[:57] + "..."

    return {
        "slide_id": str(uuid4()),
        "slide_type": original_slide["slide_type"],
        "slide_index": original_slide.get("slide_index", 0) + 0.5,
        "action_title": title,
        "content": {
            "layout_variant": original_slide.get("content", {}).get("layout_variant", "single_column"),
            "bullets": overflow_bullets,
        },
        "outline_context": {
            **original_slide.get("outline_context", {}),
            "parent_section_id": original_slide["slide_id"],
        },
        "layout_hints": original_slide.get("layout_hints", {}),
        "ai_metadata": {
            "generation_confidence": 1.0,
            "human_review_status": "pending",
            "hallucination_risk_flags": [],
        },
        "validation_state": {
            "schema_compliant": True,
            "blocking_errors": [],
            "layout_warnings": ["auto_split_continuation"],
        },
    }


def reconcile_slide_indices(slides: List[dict]) -> List[dict]:
    """
    Convert fractional slide_index values back to proper integers.

    Args:
        slides: List of slide dicts that may have fractional slide_index values

    Returns:
        Slides with corrected integer slide_index values
    """
    sorted_slides = sorted(slides, key=lambda s: float(s.get("slide_index", 0)))

    for i, slide in enumerate(sorted_slides):
        slide["slide_index"] = i

    return sorted_slides