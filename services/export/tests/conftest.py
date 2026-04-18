import pytest
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def sample_theme_tokens():
    """Return sample theme tokens for testing."""
    from engine.theme_resolver import resolve_theme
    return resolve_theme("modern_light")


@pytest.fixture
def sample_deck():
    """Return a minimal valid deck for testing."""
    return {
        "presentation_id": "550e8400-e29b-41d4-a716-446655440000",
        "schema_version": "1.0.0",
        "aspect_ratio": "16:9",
        "metadata": {
            "title": "Test Deck",
            "theme": "modern_light",
            "language": "en-US"
        },
        "slides": [
            {
                "slide_id": "slide-1",
                "slide_type": "title_slide",
                "slide_index": 0,
                "action_title": "Test Action Title",
                "content": {
                    "headline": "Test Headline"
                },
                "validation_state": {
                    "schema_compliant": True,
                    "blocking_errors": [],
                }
            }
        ],
        "validation_state": {
            "schema_compliant": True,
            "blocking_errors": [],
        }
    }


@pytest.fixture
def sample_layout_solutions():
    """Return sample layout solutions for testing."""
    return {
        "slide-1": {
            "slide_id": "slide-1",
            "relaxation_tier": 1,
            "is_rtl": False,
            "elements": {
                "title": {
                    "x": 60, "y": 72, "width": 880, "height": 100,
                    "font_size_units": 48, "font_size_px": 32,
                    "z_index": 200, "text_align": "center"
                }
            }
        }
    }
