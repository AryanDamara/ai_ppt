"""
Tests for relaxation and slide re-indexing — Module 11.
"""

import pytest
from ...services.layout.relaxation import (
    reconcile_slide_indices,
    build_continuation_slide,
    apply_relaxation_result,
)


def test_reconcile_slide_indices_simple():
    """Simple sequential indices should remain unchanged."""
    slides = [
        {"slide_id": "1", "slide_index": 0},
        {"slide_id": "2", "slide_index": 1},
        {"slide_id": "3", "slide_index": 2},
    ]
    result = reconcile_slide_indices(slides)
    assert [s["slide_index"] for s in result] == [0, 1, 2]


def test_reconcile_slide_indices_with_fractional():
    """Fractional indices (continuation slides) should be re-indexed."""
    slides = [
        {"slide_id": "1", "slide_index": 0},
        {"slide_id": "2", "slide_index": 1},
        {"slide_id": "2-cont", "slide_index": 1.5},
        {"slide_id": "3", "slide_index": 2},
    ]
    result = reconcile_slide_indices(slides)
    assert [s["slide_index"] for s in result] == [0, 1, 2, 3]


def test_reconcile_slide_indices_unordered():
    """Unordered slides should be sorted before re-indexing."""
    slides = [
        {"slide_id": "3", "slide_index": 2},
        {"slide_id": "1", "slide_index": 0},
        {"slide_id": "2", "slide_index": 1},
    ]
    result = reconcile_slide_indices(slides)
    assert [s["slide_index"] for s in result] == [0, 1, 2]


def test_reconcile_slide_indices_multiple_continuations():
    """Multiple continuation slides should be handled."""
    slides = [
        {"slide_id": "1", "slide_index": 0},
        {"slide_id": "2", "slide_index": 1},
        {"slide_id": "2-cont1", "slide_index": 1.5},
        {"slide_id": "2-cont2", "slide_index": 1.7},
        {"slide_id": "3", "slide_index": 2},
    ]
    result = reconcile_slide_indices(slides)
    assert [s["slide_index"] for s in result] == [0, 1, 2, 3, 4]


def test_build_continuation_slide():
    """Continuation slide should inherit properties from parent."""
    original = {
        "slide_id": "parent-123",
        "slide_type": "content_bullets",
        "slide_index": 2,
        "action_title": "Revenue Growth Q3",
        "content": {
            "layout_variant": "single_column",
            "bullets": []
        },
        "outline_context": {"section": "financials"},
        "layout_hints": {"priority": "text_primary"},
        "ai_metadata": {
            "generation_confidence": 0.95,
        }
    }
    overflow = [{"element_id": "b1", "text": "Extra bullet"}]

    cont = build_continuation_slide(original, overflow)

    assert cont["slide_type"] == "content_bullets"
    assert cont["slide_index"] == 2.5
    assert cont["outline_context"]["parent_section_id"] == "parent-123"
    assert cont["content"]["bullets"] == overflow
    assert "auto_split_continuation" in cont["validation_state"]["layout_warnings"]


def test_apply_relaxation_result_font_scale():
    """Font scale should be clamped to [0.8, 1.2]."""
    from ...services.layout.relaxation import RelaxationResult
    from ...services.layout.cassowary_solver import LayoutSolution

    solution = LayoutSolution(
        slide_id="test",
        relaxation_tier=2,
        solve_time_ms=5.0,
        warnings=[],
        elements={},
        font_scale_override=0.75,  # Below minimum
    )

    result = RelaxationResult(
        solution=solution,
        font_scale_to_write=0.75,
        layout_warnings_to_write=["text_overflow"],
    )

    slide = {"slide_id": "test"}
    updated = apply_relaxation_result(slide, result)

    # Should be clamped to 0.8
    assert updated["template"]["overrides"]["font_scale"] == 0.8


def test_apply_relaxation_result_clamps_upper():
    """Font scale should be clamped to max 1.2."""
    from ...services.layout.relaxation import RelaxationResult
    from ...services.layout.cassowary_solver import LayoutSolution

    solution = LayoutSolution(
        slide_id="test",
        relaxation_tier=1,
        solve_time_ms=5.0,
        warnings=[],
        elements={},
        font_scale_override=1.5,  # Above maximum
    )

    result = RelaxationResult(
        solution=solution,
        font_scale_to_write=1.5,
        layout_warnings_to_write=[],
    )

    slide = {"slide_id": "test"}
    updated = apply_relaxation_result(slide, result)

    # Should be clamped to 1.2
    assert updated["template"]["overrides"]["font_scale"] == 1.2