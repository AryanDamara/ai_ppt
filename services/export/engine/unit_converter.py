"""
Unit converter for the PPTX export engine.

NEVER import Inches() from python-pptx in any builder file.
ALWAYS use units_to_emu() from this module.

All coordinates from Phase 2 LayoutSolution are in layout units.
All coordinates python-pptx expects are in EMU (English Metric Units).
"""

from typing import Literal

# ── Type aliases ──────────────────────────────────────────────────────────────
AspectRatio = Literal["4:3", "16:9"]
Axis = Literal["x", "y", "width", "height"]

# ── Slide geometry constants ───────────────────────────────────────────────────
SLIDE_WIDTH_UNITS: int = 1000
ASPECT_RATIO_HEIGHT_UNITS: dict[str, int] = {
    "4:3":  750,
    "16:9": 562,
}

# PowerPoint standard physical dimensions
# 16:9 is the modern default for new presentations
PPTX_SLIDE_WIDTH_INCHES: float  = 13.333
PPTX_SLIDE_HEIGHT_INCHES: float = 7.5
EMU_PER_INCH: int = 914_400

# Pre-computed totals (used in EMU math below)
SLIDE_WIDTH_EMU:  int = int(PPTX_SLIDE_WIDTH_INCHES  * EMU_PER_INCH)  # 12_192_756
SLIDE_HEIGHT_EMU: int = int(PPTX_SLIDE_HEIGHT_INCHES * EMU_PER_INCH)  # 6_858_000

# Layout zones (in layout units) — matches Phase 2 template definitions
SAFE_AREA_MARGIN_LEFT:   int = 60
SAFE_AREA_MARGIN_RIGHT:  int = 60
SAFE_AREA_MARGIN_TOP:    int = 72
FOOTER_ZONE_Y_UNITS:     int = 710   # Footer zone begins here (layout units)


def units_to_emu(
    units: float,
    axis: Axis,
    aspect_ratio: AspectRatio = "16:9",
) -> int:
    """
    Convert layout units to EMU for python-pptx positioning.

    This is THE canonical conversion function. Import and call it everywhere.
    Do not write inline math. Do not import Inches() in builder files.

    Parameters
    ----------
    units : float
        Value in layout units. x/width: range 0–1000. y/height: range 0–562 (16:9)
        or 0–750 (4:3).
    axis : Axis
        'x' or 'width' → uses slide WIDTH scale (1000 units = 13.333 inches)
        'y' or 'height' → uses slide HEIGHT scale (562/750 units = 7.5 inches)
    aspect_ratio : AspectRatio
        "16:9" (default, most common) or "4:3"

    Returns
    -------
    int
        EMU value suitable for python-pptx shape positioning arguments.

    Examples
    --------
    >>> units_to_emu(0, 'x')            # Left edge
    0
    >>> units_to_emu(1000, 'x')         # Right edge (full width)
    12192756
    >>> units_to_emu(562, 'y', '16:9')  # Bottom edge, 16:9
    6858000
    >>> units_to_emu(750, 'y', '4:3')   # Bottom edge, 4:3 (same physical height)
    6858000
    >>> units_to_emu(500, 'x')          # Horizontal centre
    6096378
    >>> units_to_emu(281, 'y', '16:9')  # Vertical centre, 16:9 (approx)
    3429000
    >>> units_to_emu(60, 'x')           # Left safe-area margin
    730965
    """
    slide_h_units = ASPECT_RATIO_HEIGHT_UNITS[aspect_ratio]

    if axis in ('x', 'width'):
        inches = (units / SLIDE_WIDTH_UNITS) * PPTX_SLIDE_WIDTH_INCHES
    else:
        # y and height — use slide HEIGHT units, not width units
        inches = (units / slide_h_units) * PPTX_SLIDE_HEIGHT_INCHES

    return int(inches * EMU_PER_INCH)


def font_units_to_pt(
    font_size_units: float,
    aspect_ratio: AspectRatio = "16:9",
) -> float:
    """
    Convert height-relative layout-unit font size to PowerPoint points.

    Phase 2 LayoutSolution stores font sizes as layout units relative to slide
    HEIGHT (because font size scales with vertical space, not horizontal).

    Use the returned value with: run.font.size = Pt(font_units_to_pt(...))

    Parameters
    ----------
    font_size_units : float
        Font size from LayoutSolution element, e.g. element['font_size_units']
    aspect_ratio : AspectRatio
        Must match the deck's aspect_ratio field.

    Returns
    -------
    float
        Font size in points (pt), rounded to 1 decimal place.

    Examples
    --------
    >>> font_units_to_pt(48, '16:9')    # Title size
    32.4
    >>> font_units_to_pt(24, '16:9')    # Body size
    16.2
    >>> font_units_to_pt(14, '16:9')    # Footer/caption size
    9.5
    """
    slide_h_units = ASPECT_RATIO_HEIGHT_UNITS[aspect_ratio]
    # Convert units → inches → pixels (at 96 DPI) → points (1pt = 1/72 inch)
    inches = (font_size_units / slide_h_units) * PPTX_SLIDE_HEIGHT_INCHES
    px = inches * 96.0     # 96 DPI reference
    pt = px * 0.75         # 1px = 0.75pt at 96 DPI
    return round(pt, 1)


def apply_font_scale(font_pt: float, font_scale: float) -> float:
    """
    Apply Phase 2 tier-2 relaxation font_scale to a computed font size.

    font_scale comes from slide.template.overrides.font_scale, written by
    Phase 2 when text was too long to fit at the default size. Range: [0.8, 1.2].

    ALWAYS clamp the raw value before multiplying — never trust it blindly.
    NEVER call this function twice on the same value.

    Parameters
    ----------
    font_pt : float
        Font size in points, from font_units_to_pt().
    font_scale : float
        Scale factor from template.overrides.font_scale. Clamped to [0.8, 1.2].

    Returns
    -------
    float
        Scaled font size in points, rounded to 1 decimal place.
    """
    clamped = max(0.8, min(1.2, float(font_scale)))
    return round(font_pt * clamped, 1)


def footer_zone_emu(aspect_ratio: AspectRatio = "16:9") -> dict[str, int]:
    """
    Return EMU coordinates for the standard footer zone.

    Footer zone starts at FOOTER_ZONE_Y_UNITS (710 layout units) and extends
    to the bottom of the slide. Used by all builders when rendering the footer.

    Returns
    -------
    dict with keys: x, y, width, height (all in EMU)
    """
    slide_h_units = ASPECT_RATIO_HEIGHT_UNITS[aspect_ratio]
    footer_height_units = slide_h_units - FOOTER_ZONE_Y_UNITS  # e.g. 562 - 710 = negative for 16:9
    # Fallback: use a minimal height if footer zone is below slide bottom
    footer_h = max(
        FOOTER_ZONE_Y_UNITS,
        slide_h_units - FOOTER_ZONE_Y_UNITS
    )
    return {
        "x":      units_to_emu(SAFE_AREA_MARGIN_LEFT, 'x', aspect_ratio),
        "y":      units_to_emu(FOOTER_ZONE_Y_UNITS, 'y', aspect_ratio),
        "width":  units_to_emu(SLIDE_WIDTH_UNITS - SAFE_AREA_MARGIN_LEFT - SAFE_AREA_MARGIN_RIGHT, 'width', aspect_ratio),
        "height": max(units_to_emu(30, 'height', aspect_ratio), 300_000),  # Minimum 300,000 EMU
    }
