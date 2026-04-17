"""
Tests for constraint validator — Module 0.
"""

import pytest
from ...services.layout.constraint_validator import (
    validate_canvas_dimensions,
    detect_bidi_text,
    preflight_check,
    ConstraintConflictType,
)


def test_validate_canvas_dimensions_valid():
    errors = validate_canvas_dimensions(1280, 720)
    assert len(errors) == 0


def test_validate_canvas_dimensions_negative():
    errors = validate_canvas_dimensions(-1, 720)
    assert any("must be > 0" in e for e in errors)


def test_validate_canvas_dimensions_exceeds_gpu_limit():
    errors = validate_canvas_dimensions(20000, 720)
    assert any("exceeds GPU texture limit" in e for e in errors)


def test_detect_bidi_text_pure_english():
    slide = {"action_title": "Hello World", "content": {"bullets": []}}
    assert detect_bidi_text(slide) is False


def test_detect_bidi_text_pure_arabic():
    slide = {"action_title": "مرحبا", "content": {"bullets": []}}
    assert detect_bidi_text(slide) is False


def test_detect_bidi_text_mixed_arabic_english():
    # Mixed LTR/RTL text
    slide = {
        "action_title": "Product XYZ-123 \u0641\u064a \u0627\u0644\u0639\u0631\u0628\u064a\u0629",
        "content": {"bullets": []}
    }
    assert detect_bidi_text(slide) is True


def test_preflight_check_valid():
    slide = {
        "action_title": "Test",
        "content": {"bullets": [{"element_id": "1", "text": "Bullet"}]}
    }
    template_zones = {
        "title": {"x": 60, "y": 72, "width": 880, "height": 80}
    }

    result = preflight_check(
        slide=slide,
        template_zones=template_zones,
        slide_w=1000,
        slide_h=562,
        canvas_px_w=1280,
        canvas_px_h=720,
        available_font_paths=["inter"],
        required_font_paths=["inter"],
    )

    assert result.is_valid is True
    assert result.canvas_valid is True
    assert len(result.conflicts) == 0


def test_preflight_check_canvas_overflow():
    slide = {"action_title": "Test", "content": {"bullets": []}}
    template_zones = {
        "title": {"x": 100, "y": 72, "width": 950, "height": 80}
    }

    result = preflight_check(
        slide=slide,
        template_zones=template_zones,
        slide_w=1000,
        slide_h=562,
        canvas_px_w=1280,
        canvas_px_h=720,
        available_font_paths=["inter"],
        required_font_paths=["inter"],
    )

    assert result.is_valid is False
    assert any(c.conflict_type == ConstraintConflictType.CANVAS_OVERFLOW for c in result.conflicts)