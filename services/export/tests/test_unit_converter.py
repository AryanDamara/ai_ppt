"""
Unit converter tests — critical path validation.

These tests verify the fundamental conversion math that underlies
EVERY coordinate, size, and font calculation in the export engine.
"""
import pytest
from engine.unit_converter import (
    units_to_emu,
    font_units_to_pt,
    apply_font_scale,
    SLIDE_WIDTH_EMU,
    SLIDE_HEIGHT_EMU,
)


class TestUnitsToEmu:
    """Tests for units_to_emu() — the canonical coordinate conversion."""

    def test_zero_x_returns_zero(self):
        """Left edge is at EMU 0."""
        assert units_to_emu(0, 'x') == 0

    def test_full_width_x(self):
        """Full width (1000 units) equals SLIDE_WIDTH_EMU."""
        assert units_to_emu(1000, 'x') == SLIDE_WIDTH_EMU

    def test_half_width_x(self):
        """Horizontal center is half of full width."""
        result = units_to_emu(500, 'x')
        expected = SLIDE_WIDTH_EMU // 2
        # Allow small rounding differences
        assert abs(result - expected) < 100

    def test_full_height_16_9(self):
        """16:9 full height (562 units) equals SLIDE_HEIGHT_EMU."""
        assert units_to_emu(562, 'y', '16:9') == SLIDE_HEIGHT_EMU

    def test_full_height_4_3(self):
        """4:3 full height (750 units) equals same physical height as 16:9."""
        assert units_to_emu(750, 'y', '4:3') == SLIDE_HEIGHT_EMU

    def test_half_height_16_9(self):
        """Vertical center for 16:9."""
        result = units_to_emu(281, 'y', '16:9')
        expected = SLIDE_HEIGHT_EMU // 2
        assert abs(result - expected) < 50000  # Within reasonable range

    def test_safe_area_margin(self):
        """Left margin (60 units) is non-zero."""
        result = units_to_emu(60, 'x')
        assert result > 0
        assert result < 1_000_000  # Should be ~730k EMU

    def test_width_axis_synonym(self):
        """'width' axis works same as 'x'."""
        x_result = units_to_emu(500, 'x')
        width_result = units_to_emu(500, 'width')
        assert x_result == width_result

    def test_height_axis_synonym(self):
        """'height' axis works same as 'y'."""
        y_result = units_to_emu(300, 'y', '16:9')
        height_result = units_to_emu(300, 'height', '16:9')
        assert y_result == height_result


class TestFontUnitsToPt:
    """Tests for font_units_to_pt() — font size conversion."""

    def test_title_size_16_9(self):
        """48 layout units for 16:9 should be ~46pt."""
        result = font_units_to_pt(48, '16:9')
        assert 44 <= result <= 48

    def test_body_size_16_9(self):
        """24 layout units for 16:9 should be ~23pt."""
        result = font_units_to_pt(24, '16:9')
        assert 22 <= result <= 25

    def test_caption_size_16_9(self):
        """14 layout units for 16:9 should be ~13.5pt."""
        result = font_units_to_pt(14, '16:9')
        assert 12 <= result <= 15

    def test_4_3_font_size(self):
        """Same layout units give smaller pt for 4:3 (750 vs 562 height units)."""
        result_16_9 = font_units_to_pt(48, '16:9')
        result_4_3 = font_units_to_pt(48, '4:3')
        # 4:3 uses more height units (750 vs 562) so same units = smaller pt
        assert result_4_3 < result_16_9
        # 4:3 should be about 75% of 16:9 (562/750)
        assert abs(result_4_3 - result_16_9 * 562/750) < 2


class TestApplyFontScale:
    """Tests for apply_font_scale() — tier-2 relaxation scaling."""

    def test_no_scale(self):
        """font_scale of 1.0 returns original size."""
        result = apply_font_scale(32.0, 1.0)
        assert result == 32.0

    def test_scale_down(self):
        """font_scale of 0.85 reduces size."""
        result = apply_font_scale(32.0, 0.85)
        assert result == 27.2

    def test_scale_up(self):
        """font_scale of 1.15 increases size."""
        result = apply_font_scale(32.0, 1.15)
        assert result == 36.8

    def test_clamp_min(self):
        """Values below 0.8 are clamped to 0.8."""
        result = apply_font_scale(32.0, 0.7)
        assert result == 25.6  # 32 * 0.8

    def test_clamp_max(self):
        """Values above 1.2 are clamped to 1.2."""
        result = apply_font_scale(32.0, 1.3)
        assert result == 38.4  # 32 * 1.2

    def test_string_input(self):
        """String numbers are converted."""
        result = apply_font_scale(32.0, "0.9")
        assert result == 28.8

    def test_rounding(self):
        """Result is rounded to 1 decimal place."""
        result = apply_font_scale(33.3, 0.85)
        # 33.3 * 0.85 = 28.305, rounded to 28.3
        assert result == 28.3
