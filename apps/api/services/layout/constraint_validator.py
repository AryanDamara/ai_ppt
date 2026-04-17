"""
Module 0 — Constraint System Pre-Validation
Pre-flight checks before Cassowary solving to prevent undefined states.
"""

from dataclasses import dataclass
from typing import List, Tuple, Optional
from enum import Enum


class ConstraintConflictType(str, Enum):
    RANGE_INFEASIBLE = "range_infeasible"
    EQUALITY_CONFLICT = "equality_conflict"
    DIMENSION_ZERO = "dimension_zero"
    CANVAS_OVERFLOW = "canvas_overflow"


@dataclass
class ConstraintConflict:
    conflict_type: ConstraintConflictType
    variable_name: str
    constraint_a: str
    constraint_b: str
    suggested_fix: str


@dataclass
class PreflightResult:
    is_valid: bool
    conflicts: List[ConstraintConflict]
    canvas_valid: bool
    fonts_available: List[str]
    fonts_missing: List[str]
    bidi_detected: bool


def validate_canvas_dimensions(canvas_px_w: int, canvas_px_h: int) -> List[str]:
    """
    Validate canvas dimensions are sane before solving.
    Returns list of error strings (empty = valid).
    """
    errors = []
    if canvas_px_w <= 0:
        errors.append(f"canvas_px_w must be > 0, got {canvas_px_w}")
    if canvas_px_h <= 0:
        errors.append(f"canvas_px_h must be > 0, got {canvas_px_h}")
    if canvas_px_w > 16384:
        errors.append(f"canvas_px_w {canvas_px_w} exceeds GPU texture limit of 16384")
    if canvas_px_h > 16384:
        errors.append(f"canvas_px_h {canvas_px_h} exceeds GPU texture limit of 16384")
    return errors


def detect_bidi_text(slide: dict) -> bool:
    """
    Detect if a slide contains mixed BiDi text (LTR embedded in RTL or vice versa).
    """
    import unicodedata

    def has_rtl_char(text: str) -> bool:
        for char in text:
            cat = unicodedata.bidirectional(char)
            if cat in ('R', 'AL', 'RLE', 'RLO', 'RLI'):
                return True
        return False

    def has_ltr_char(text: str) -> bool:
        for char in text:
            cat = unicodedata.bidirectional(char)
            if cat in ('L', 'LRE', 'LRO', 'LRI'):
                return True
        return False

    all_texts = []

    action_title = slide.get("action_title", "")
    if action_title:
        all_texts.append(action_title)

    content = slide.get("content", {})
    bullets = content.get("bullets", [])
    for bullet in bullets:
        if bullet.get("text"):
            all_texts.append(bullet["text"])

    for text in all_texts:
        if has_rtl_char(text) and has_ltr_char(text):
            return True

    return False


def preflight_check(
    slide: dict,
    template_zones: dict,
    slide_w: int,
    slide_h: int,
    canvas_px_w: int,
    canvas_px_h: int,
    available_font_paths: List[str],
    required_font_paths: List[str],
) -> PreflightResult:
    """
    Run all pre-flight checks before attempting to solve.
    Called at the top of CassowarySlideSolver.solve().
    """
    conflicts = []

    canvas_errors = validate_canvas_dimensions(canvas_px_w, canvas_px_h)
    canvas_valid = len(canvas_errors) == 0

    for zone_id, bounds in template_zones.items():
        if bounds.get("x", 0) + bounds.get("width", 0) > slide_w:
            conflicts.append(ConstraintConflict(
                conflict_type=ConstraintConflictType.CANVAS_OVERFLOW,
                variable_name=f"{zone_id}.right",
                constraint_a=f"{zone_id}.x({bounds.get('x')}) + {zone_id}.width({bounds.get('width')})",
                constraint_b=f"slide_width({slide_w})",
                suggested_fix=f"Reduce {zone_id}.width by {bounds.get('x', 0) + bounds.get('width', 0) - slide_w} units",
            ))

        if bounds.get("y", 0) + bounds.get("height", 0) > slide_h:
            conflicts.append(ConstraintConflict(
                conflict_type=ConstraintConflictType.CANVAS_OVERFLOW,
                variable_name=f"{zone_id}.bottom",
                constraint_a=f"{zone_id}.y({bounds.get('y')}) + {zone_id}.height({bounds.get('height')})",
                constraint_b=f"slide_height({slide_h})",
                suggested_fix=f"Reduce {zone_id}.height or y position",
            ))

    fonts_missing = [p for p in required_font_paths if p not in available_font_paths]
    fonts_available = [p for p in required_font_paths if p in available_font_paths]

    bidi = detect_bidi_text(slide)

    return PreflightResult(
        is_valid=len(conflicts) == 0 and canvas_valid,
        conflicts=conflicts,
        canvas_valid=canvas_valid,
        fonts_available=fonts_available,
        fonts_missing=fonts_missing,
        bidi_detected=bidi,
    )