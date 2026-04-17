"""
Tests for i18n profiles — Module 4.
"""

import pytest
from ...services.layout.i18n_profiles import (
    get_profile,
    LATIN,
    CJK,
    RTL,
    shouldMirrorElement,
    flipXCoordinate,
    flipVisualAnchor,
)


def test_get_profile_english():
    profile = get_profile("en")
    assert profile.script == "latin"
    assert profile.rtl is False


def test_get_profile_chinese():
    profile = get_profile("zh")
    assert profile.script == "cjk"
    assert profile.line_height_multiplier == 1.75


def test_get_profile_arabic():
    profile = get_profile("ar")
    assert profile.script == "rtl"
    assert profile.rtl is True
    assert profile.mirror_horizontal is True


def test_cjk_higher_line_height():
    """CJK requires more line spacing."""
    assert CJK.line_height_multiplier > LATIN.line_height_multiplier


def test_cjk_lower_max_font_size():
    """CJK max font size is lower due to complex characters."""
    assert CJK.max_body_font_size_px < LATIN.max_body_font_size_px


def test_rtl_text_align():
    assert RTL.text_align() == "right"


def test_latin_text_align():
    assert LATIN.text_align() == "left"


def test_flip_x_coordinate():
    """In RTL, x=100, width=200 should flip to x=700."""
    result = flipXCoordinate(100, 200, 1000)
    assert result == 700


def test_flip_visual_anchor():
    """Left anchor should flip to right in RTL."""
    result = flipVisualAnchor("left", RTL)
    assert result == "right"


def test_flip_visual_anchor_latin_unchanged():
    """Latin profile doesn't flip anchors."""
    result = flipVisualAnchor("left", LATIN)
    assert result == "left"


def test_should_mirror_text_element():
    """Text elements should mirror in RTL."""
    result = shouldMirrorElement(RTL, "body")
    assert result is True


def test_should_not_mirror_chart():
    """Charts should NOT mirror in RTL."""
    result = shouldMirrorElement(RTL, "chart")
    assert result is False


def test_should_not_mirror_image():
    """Images should NOT mirror in RTL."""
    result = shouldMirrorElement(RTL, "image")
    assert result is False


def test_directional_icon_should_flip():
    """Directional icons should flip."""
    result = shouldMirrorElement(RTL, "icon", "arrow_right")
    assert result is True


def test_non_directional_icon_should_not_flip():
    """Non-directional icons should not flip."""
    result = shouldMirrorElement(RTL, "icon", "search")
    assert result is False


def test_bidi_override_rtl():
    """RTL should return RLI character."""
    override = RTL.get_bidi_override()
    assert override == "\u2067"


def test_bidi_override_ltr():
    """LTR should return LRI character."""
    override = LATIN.get_bidi_override()
    assert override == "\u2066"