"""
Tests for BiDi detection and handling.
"""

import pytest
from ...services.layout.constraint_validator import detect_bidi_text


def test_bidi_pure_english():
    """Pure English should NOT trigger BiDi."""
    slide = {
        "action_title": "Q3 Revenue Growth Exceeded Forecast",
        "content": {
            "bullets": [
                {"text": "Enterprise segment drove 78% of growth"},
                {"text": "APAC region outperformed by 22 points"},
            ]
        }
    }
    assert detect_bidi_text(slide) is False


def test_bidi_mixed_arabic_english():
    """Arabic with embedded English should trigger BiDi."""
    slide = {
        "action_title": "\u0645\u0646\u062a\u062c Product XYZ-123 \u0641\u064a \u0627\u0644\u0645\u062a\u062c\u0631",
        "content": {"bullets": []}
    }
    assert detect_bidi_text(slide) is True


def test_bidi_hebrew_with_numbers():
    """Hebrew with embedded numbers should trigger BiDi."""
    slide = {
        "action_title": "\u05de\u05db\u05d9\u05e8\u05d4 \u05d4\u05d2\u05d9\u05e2\u05d4 \u05dc-78%",
        "content": {"bullets": []}
    }
    assert detect_bidi_text(slide) is True


def test_bidi_url_in_arabic():
    """URL embedded in Arabic text should trigger BiDi."""
    slide = {
        "action_title": "\u0627\u0632\u0631\u0639 https://example.com \u0644\u0644\u0645\u0632\u064a\u062f",
        "content": {"bullets": []}
    }
    assert detect_bidi_text(slide) is True


def test_bidi_pure_cjk():
    """Pure CJK should NOT trigger BiDi (no direction mixing)."""
    slide = {
        "action_title": "\u7b2c\u4e09\u5b63\u5ea6\u6536\u5165\u589e\u957f\u8d85\u51fa\u9884\u671f",
        "content": {"bullets": [{"text": "\u4f01\u4e1a\u5e02\u573a\u589e\u957f78%"}]}
    }
    assert detect_bidi_text(slide) is False