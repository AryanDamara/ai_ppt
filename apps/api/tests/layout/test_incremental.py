"""
Tests for incremental solver — Module 6 (frontend logic).
"""

import pytest

# Import frontend logic (these would need proper module setup)
# For now, testing the logic directly


def test_compute_impact_radius_theme_change():
    """Theme change should impact entire deck."""
    from ...services.layout.incremental_solver import computeImpactRadius
    radius = computeImpactRadius("metadata.theme", 5, 10)
    assert radius == "deck"


def test_compute_impact_radius_language_change():
    """Language change should impact entire deck."""
    from ...services.layout.incremental_solver import computeImpactRadius
    radius = computeImpactRadius("metadata.language", 5, 10)
    assert radius == "deck"


def test_compute_impact_radius_bullet_text():
    """Bullet text edit should impact only element."""
    from ...services.layout.incremental_solver import computeImpactRadius
    radius = computeImpactRadius("content.bullets[0].text", 5, 10)
    assert radius == "element"


def test_compute_impact_radius_content():
    """Content change should impact slide."""
    from ...services.layout.incremental_solver import computeImpactRadius
    radius = computeImpactRadius("content.bullets", 5, 10)
    assert radius == "slide"


def test_compute_impact_radius_action_title():
    """Action title change should impact slide."""
    from ...services.layout.incremental_solver import computeImpactRadius
    radius = computeImpactRadius("action_title", 5, 10)
    assert radius == "slide"


def test_get_slides_to_resolve_element():
    """Element-level change affects only one slide."""
    from ...services.layout.incremental_solver import getSlidesToResolve

    slides = [
        {"slide_id": "s1", "slide_index": 0},
        {"slide_id": "s2", "slide_index": 1},
    ]
    result = getSlidesToResolve("element", "s1", slides, {})
    assert result == ["s1"]


def test_get_slides_to_resolve_deck():
    """Deck-level change affects all slides."""
    from ...services.layout.incremental_solver import getSlidesToResolve

    slides = [
        {"slide_id": "s1", "slide_index": 0},
        {"slide_id": "s2", "slide_index": 1},
        {"slide_id": "s3", "slide_index": 2},
    ]
    result = getSlidesToResolve("deck", "s1", slides, {})
    assert result == ["s1", "s2", "s3"]


class MockContentHashRegistry:
    """Mock implementation for testing."""
    def __init__(self):
        self.hashes = {}

    def hasChanged(self, slide):
        current = hash(str(slide))
        previous = self.hashes.get(slide.get("slide_id"))
        return current != previous

    def markSolved(self, slide):
        self.hashes[slide.get("slide_id")] = hash(str(slide))

    def invalidate(self, slide_id):
        self.hashes.pop(slide_id, None)


def test_content_hash_registry_detects_change():
    """Registry should detect content changes."""
    registry = MockContentHashRegistry()
    slide = {"slide_id": "s1", "action_title": "Hello"}

    registry.markSolved(slide)
    assert not registry.hasChanged(slide)

    slide["action_title"] = "World"
    assert registry.hasChanged(slide)


def test_content_hash_registry_invalidate():
    """Invalidate should force re-check."""
    registry = MockContentHashRegistry()
    slide = {"slide_id": "s1", "action_title": "Hello"}

    registry.markSolved(slide)
    registry.invalidate("s1")
    assert registry.hasChanged(slide)