"""
Tests for unit converter — Module 1.
Critical: verify aspect ratio correctness for EMU conversion.
"""

import pytest
from ...services.layout.unit_converter import (
    units_to_emu,
    units_to_css_px,
    units_to_pt,
    css_px_to_units,
    get_slide_metrics,
    ASPECT_RATIO_HEIGHT,
)


def test_units_to_emu_width_16_9():
    """500 units x should be 50% of slide width in EMU."""
    emu = units_to_emu(500, 'x', '16:9')
    # 500/1000 * 13.333in * 914400 EMU/in = 6095670 EMU
    expected = int(0.5 * 13.333 * 914400)
    assert emu == expected


def test_units_to_emu_height_16_9():
    """281 units y should be 50% of slide height (562) in EMU."""
    emu = units_to_emu(281, 'y', '16:9')
    # 281/562 * 7.5in * 914400 EMU/in = 3429000 EMU
    expected = int(0.5 * 7.5 * 914400)
    assert emu == expected


def test_units_to_emu_height_4_3():
    """375 units y should be 50% of slide height (750) in EMU."""
    emu = units_to_emu(375, 'y', '4:3')
    # 375/750 * 7.5in * 914400 EMU/in = 3429000 EMU
    expected = int(0.5 * 7.5 * 914400)
    assert emu == expected


def test_16_9_vs_4_3_height_different():
    """CRITICAL: 16:9 and 4:3 must produce different EMU for same y units."""
    emu_16_9 = units_to_emu(281, 'y', '16:9')
    emu_4_3 = units_to_emu(281, 'y', '4:3')
    assert emu_16_9 != emu_4_3


def test_units_to_css_px():
    m = get_slide_metrics('16:9', 1280, 720)
    px = units_to_css_px(500, 'x', m)
    assert px == 640  # 50% of 1280


def test_units_to_css_px_height():
    m = get_slide_metrics('16:9', 1280, 720)
    px = units_to_css_px(281, 'y', m)
    assert px == 360  # 50% of 720 (because 562 units = 720px)


def test_css_px_to_units_roundtrip():
    m = get_slide_metrics('16:9', 1280, 720)
    original = 640
    units = css_px_to_units(original, 'x', m)
    back = units_to_css_px(units, 'x', m)
    assert abs(back - original) < 0.1


def test_units_to_pt():
    pt = units_to_pt(500, 'x', '16:9')
    # 500/1000 * 13.333in * 72pt/in = 480pt
    expected = 0.5 * 13.333 * 72
    assert abs(pt - expected) < 0.01