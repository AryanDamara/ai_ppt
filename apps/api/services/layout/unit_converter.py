"""
Module 1 — Unit Converter (DPR-Aware)
Converts between layout units, CSS pixels, physical pixels, EMU, and points.
"""

from dataclasses import dataclass
from typing import Literal

AspectRatio = Literal["4:3", "16:9"]

ASPECT_RATIO_HEIGHT = {"4:3": 750, "16:9": 562}
SLIDE_WIDTH_UNITS = 1000

# PowerPoint standard dimensions
PPTX_SLIDE_WIDTH_INCHES = 13.333
PPTX_SLIDE_HEIGHT_INCHES = 7.5
EMU_PER_INCH = 914400


@dataclass
class SlideMetrics:
    aspect_ratio: AspectRatio
    units_w: int
    units_h: int
    canvas_px_w: int
    canvas_px_h: int
    dpr: float = 1.0


def get_slide_metrics(aspect_ratio: AspectRatio, canvas_px_w: int, canvas_px_h: int, dpr: float = 1.0) -> SlideMetrics:
    return SlideMetrics(
        aspect_ratio=aspect_ratio,
        units_w=SLIDE_WIDTH_UNITS,
        units_h=ASPECT_RATIO_HEIGHT[aspect_ratio],
        canvas_px_w=canvas_px_w,
        canvas_px_h=canvas_px_h,
        dpr=dpr,
    )


def units_to_css_px(units: float, axis: str, m: SlideMetrics) -> float:
    """Convert layout units to CSS pixels (logical pixels, NOT physical)."""
    if axis in ('x', 'width'):
        return (units / m.units_w) * m.canvas_px_w
    return (units / m.units_h) * m.canvas_px_h


def units_to_physical_px(units: float, axis: str, m: SlideMetrics) -> float:
    """
    Convert layout units to physical pixels (multiply by DPR).
    Use this for Canvas API drawing and text measurement.
    Never use this for CSS positioning.
    """
    return units_to_css_px(units, axis, m) * m.dpr


def units_to_emu(units: float, axis: str, aspect_ratio: AspectRatio = "16:9") -> int:
    """
    Convert layout units to EMU for PPTX export.

    CRITICAL FIX: The height divisor depends on aspect ratio.
    16:9 uses 562 units for height, NOT 750.
    4:3 uses 750 units for height.

    Never use Inches() from python-pptx directly. Always use this function.
    """
    slide_h_units = ASPECT_RATIO_HEIGHT[aspect_ratio]
    if axis in ('x', 'width'):
        inches = (units / SLIDE_WIDTH_UNITS) * PPTX_SLIDE_WIDTH_INCHES
    else:
        inches = (units / slide_h_units) * PPTX_SLIDE_HEIGHT_INCHES
    return int(inches * EMU_PER_INCH)


def units_to_pt(units: float, axis: str, aspect_ratio: AspectRatio = "16:9") -> float:
    """Convert layout units to PDF points (72 per inch)."""
    slide_h_units = ASPECT_RATIO_HEIGHT[aspect_ratio]
    if axis in ('x', 'width'):
        inches = (units / SLIDE_WIDTH_UNITS) * PPTX_SLIDE_WIDTH_INCHES
    else:
        inches = (units / slide_h_units) * PPTX_SLIDE_HEIGHT_INCHES
    return inches * 72.0


def css_px_to_units(px: float, axis: str, m: SlideMetrics) -> float:
    if axis in ('x', 'width'):
        return (px / m.canvas_px_w) * m.units_w
    return (px / m.canvas_px_h) * m.units_h


def font_px_to_units(font_size_px: float, m: SlideMetrics) -> float:
    """Font sizes are always height-relative."""
    return (font_size_px / m.canvas_px_h) * m.units_h


DEFAULT_METRICS = get_slide_metrics("16:9", 1280, 720, dpr=1.0)