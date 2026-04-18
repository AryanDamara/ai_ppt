"""
Theme token system for the export engine.

A ThemeTokens object holds every color and font reference a slide builder needs.
Builder files NEVER hardcode hex values or font names — they always read from tokens.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Tuple
from pptx.dml.color import RgbColor

# RGB type alias for clarity
RGB = Tuple[int, int, int]


@dataclass
class ThemeTokens:
    """
    All design tokens for one theme.
    RGB tuples are (red, green, blue) integers in range 0–255.
    """
    name: str

    # ── Backgrounds ───────────────────────────────────────────────────────────
    slide_background_rgb: RGB      # Slide fill color

    # ── Typography colors ─────────────────────────────────────────────────────
    title_rgb:     RGB             # Slide title / action_title
    body_rgb:      RGB             # Bullet text, table cells, body text
    subtitle_rgb:  RGB             # Subheadings, subdued body text
    footer_rgb:    RGB             # Footer zone text (slide number, source)

    # ── Accent colors ─────────────────────────────────────────────────────────
    accent_primary_rgb:   RGB     # Bold highlights, key callouts, emphasis="highlight"
    accent_secondary_rgb: RGB     # Supporting_data text, secondary highlights

    # ── Table-specific ────────────────────────────────────────────────────────
    table_header_bg_rgb:     RGB  # Header row background
    table_header_text_rgb:   RGB  # Header row text
    table_row_alt_bg_rgb:    RGB  # Alternating (odd) row background
    table_highlight_bg_rgb:  RGB  # highlight_cells background
    table_border_rgb:        RGB  # Cell border color

    # ── Section divider ───────────────────────────────────────────────────────
    section_number_rgb: RGB       # "01" section number
    section_title_rgb:  RGB       # Large section name

    # ── Font references ───────────────────────────────────────────────────────
    body_font_path:     str       # Relative to /app/fonts/, e.g. "inter/Inter-Regular.ttf"
    display_font_path:  str       # Display / heading font path
    body_font_name:     str       # Name as used in PowerPoint (must match embedded font)
    display_font_name:  str       # Display font name for PowerPoint

    # ── Chart color palette ───────────────────────────────────────────────────
    chart_palette: list[RGB] = field(default_factory=list)
    # Ordered list of RGB tuples for chart series 0, 1, 2, ...
    # Cycles if more series than palette entries.

    # ── Convenience helpers ───────────────────────────────────────────────────

    def pptx_rgb(self, rgb: RGB) -> RgbColor:
        """Convert an RGB tuple to python-pptx RgbColor."""
        return RgbColor(rgb[0], rgb[1], rgb[2])

    def series_color(self, series_index: int) -> RGB:
        """Get chart series color, cycling through palette."""
        if not self.chart_palette:
            return (79, 70, 229)  # Default indigo
        return self.chart_palette[series_index % len(self.chart_palette)]


# ── Theme definitions ──────────────────────────────────────────────────────────

_CORPORATE_DARK = ThemeTokens(
    name="corporate_dark",
    slide_background_rgb=(15, 23, 42),       # Deep navy #0F172A
    title_rgb=(248, 250, 252),               # Near-white #F8FAFC
    body_rgb=(203, 213, 225),                # Slate-300 #CBD5E1
    subtitle_rgb=(148, 163, 184),          # Slate-400 #94A3B0
    footer_rgb=(71, 85, 105),                # Slate-600 #475569
    accent_primary_rgb=(99, 102, 241),        # Indigo-500 #6366F1
    accent_secondary_rgb=(167, 139, 250),  # Violet-400 #A78BFA
    table_header_bg_rgb=(30, 41, 59),        # Slate-800 #1E293B
    table_header_text_rgb=(248, 250, 252),   # White-ish #F8FAFC
    table_row_alt_bg_rgb=(22, 30, 46),       # Even darker #161E2E
    table_highlight_bg_rgb=(49, 46, 129),    # Indigo-900 #312E81
    table_border_rgb=(51, 65, 85),           # Slate-700 #334155
    section_number_rgb=(99, 102, 241),       # Indigo-500
    section_title_rgb=(248, 250, 252),       # Near-white
    body_font_path="inter/Inter-Regular.ttf",
    display_font_path="inter/Inter-Bold.ttf",
    body_font_name="Inter",
    display_font_name="Inter",
    chart_palette=[
        (99, 102, 241),   # Indigo-500
        (167, 139, 250),  # Violet-400
        (52, 211, 153),   # Emerald-400
        (251, 191, 36),   # Amber-400
        (248, 113, 113),  # Red-400
        (56, 189, 248),   # Sky-400
    ],
)

_MODERN_LIGHT = ThemeTokens(
    name="modern_light",
    slide_background_rgb=(255, 255, 255),    # Pure white
    title_rgb=(15, 23, 42),                  # Near-black #0F172A
    body_rgb=(51, 65, 85),                   # Slate-700 #334155
    subtitle_rgb=(100, 116, 139),            # Slate-500 #64748B
    footer_rgb=(148, 163, 184),              # Slate-400 #94A3B0
    accent_primary_rgb=(79, 70, 229),        # Indigo-600 #4F46E5
    accent_secondary_rgb=(124, 58, 237),     # Violet-600 #7C3AED
    table_header_bg_rgb=(15, 23, 42),        # Near-black
    table_header_text_rgb=(255, 255, 255),   # White
    table_row_alt_bg_rgb=(248, 250, 252),    # Slate-50 #F8FAFC
    table_highlight_bg_rgb=(238, 242, 255),  # Indigo-50 #EEF2FF
    table_border_rgb=(226, 232, 240),        # Slate-200 #E2E8F0
    section_number_rgb=(79, 70, 229),        # Indigo-600
    section_title_rgb=(15, 23, 42),          # Near-black
    body_font_path="inter/Inter-Regular.ttf",
    display_font_path="playfair/PlayfairDisplay-Regular.ttf",
    body_font_name="Inter",
    display_font_name="Playfair Display",
    chart_palette=[
        (79, 70, 229),    # Indigo-600
        (124, 58, 237),   # Violet-600
        (16, 185, 129),   # Emerald-500
        (245, 158, 11),   # Amber-500
        (239, 68, 68),    # Red-500
        (14, 165, 233),   # Sky-500
    ],
)

_STARTUP_MINIMAL = ThemeTokens(
    name="startup_minimal",
    slide_background_rgb=(250, 250, 249),    # Stone-50 #FAFAF9
    title_rgb=(28, 25, 23),                  # Stone-900 #1C1917
    body_rgb=(68, 64, 60),                   # Stone-700 #44403C
    subtitle_rgb=(120, 113, 108),            # Stone-500 #78716C
    footer_rgb=(168, 162, 158),              # Stone-400 #A8A29E
    accent_primary_rgb=(234, 88, 12),        # Orange-600 #EA580C
    accent_secondary_rgb=(249, 115, 22),     # Orange-500 #F97316
    table_header_bg_rgb=(28, 25, 23),        # Stone-900
    table_header_text_rgb=(250, 250, 249),   # Stone-50
    table_row_alt_bg_rgb=(245, 245, 244),    # Stone-100 #F5F5F4
    table_highlight_bg_rgb=(255, 237, 213),  # Orange-100 #FFEDD5
    table_border_rgb=(231, 229, 228),        # Stone-200 #E7E5E4
    section_number_rgb=(234, 88, 12),        # Orange-600
    section_title_rgb=(28, 25, 23),          # Stone-900
    body_font_path="inter/Inter-Regular.ttf",
    display_font_path="inter/Inter-Bold.ttf",
    body_font_name="Inter",
    display_font_name="Inter",
    chart_palette=[
        (234, 88, 12),    # Orange-600
        (249, 115, 22),   # Orange-500
        (251, 191, 36),   # Amber-400
        (52, 211, 153),   # Emerald-400
        (14, 165, 233),   # Sky-500
        (167, 139, 250),  # Violet-400
    ],
)

_HEALTHCARE_CLINICAL = ThemeTokens(
    name="healthcare_clinical",
    slide_background_rgb=(255, 255, 255),    # White
    title_rgb=(7, 89, 133),                  # Sky-800 #075985
    body_rgb=(30, 58, 78),                   # Slate-900ish #1E3A4E
    subtitle_rgb=(71, 119, 148),             # Muted teal-blue #477794
    footer_rgb=(148, 163, 184),              # Slate-400
    accent_primary_rgb=(6, 148, 162),        # Cyan-600 #0694A2
    accent_secondary_rgb=(16, 185, 129),     # Emerald-500 #10B981
    table_header_bg_rgb=(7, 89, 133),        # Sky-800
    table_header_text_rgb=(255, 255, 255),   # White
    table_row_alt_bg_rgb=(240, 249, 255),    # Sky-50 #F0F9FF
    table_highlight_bg_rgb=(207, 250, 254),  # Cyan-100 #CFFAFE
    table_border_rgb=(186, 230, 253),        # Sky-200 #BAE6FD
    section_number_rgb=(6, 148, 162),        # Cyan-600
    section_title_rgb=(7, 89, 133),          # Sky-800
    body_font_path="inter/Inter-Regular.ttf",
    display_font_path="inter/Inter-Bold.ttf",
    body_font_name="Inter",
    display_font_name="Inter",
    chart_palette=[
        (6, 148, 162),    # Cyan-600
        (16, 185, 129),   # Emerald-500
        (7, 89, 133),     # Sky-800
        (14, 165, 233),   # Sky-500
        (52, 211, 153),   # Emerald-400
        (245, 158, 11),   # Amber-500
    ],
)

_FINANCIAL_FORMAL = ThemeTokens(
    name="financial_formal",
    slide_background_rgb=(255, 255, 255),    # White
    title_rgb=(17, 24, 39),                  # Gray-900 #111827
    body_rgb=(31, 41, 55),                   # Gray-800 #1F2937
    subtitle_rgb=(75, 85, 99),               # Gray-600 #4B5563
    footer_rgb=(156, 163, 175),              # Gray-400 #9CA3AF
    accent_primary_rgb=(5, 150, 105),        # Emerald-600 #059669
    accent_secondary_rgb=(16, 185, 129),     # Emerald-500 #10B981
    table_header_bg_rgb=(17, 24, 39),        # Gray-900
    table_header_text_rgb=(255, 255, 255),   # White
    table_row_alt_bg_rgb=(249, 250, 251),    # Gray-50 #F9FAFB
    table_highlight_bg_rgb=(209, 250, 229),  # Emerald-100 #D1FAE5
    table_border_rgb=(209, 213, 219),        # Gray-300 #D1D5DB
    section_number_rgb=(5, 150, 105),        # Emerald-600
    section_title_rgb=(17, 24, 39),          # Gray-900
    body_font_path="inter/Inter-Regular.ttf",
    display_font_path="playfair/PlayfairDisplay-Regular.ttf",
    body_font_name="Inter",
    display_font_name="Playfair Display",
    chart_palette=[
        (5, 150, 105),    # Emerald-600
        (16, 185, 129),   # Emerald-500
        (17, 24, 39),     # Gray-900
        (245, 158, 11),   # Amber-500
        (239, 68, 68),    # Red-500
        (14, 165, 233),   # Sky-500
    ],
)

# ── Theme registry ─────────────────────────────────────────────────────────────

_THEME_REGISTRY: dict[str, ThemeTokens] = {
    "corporate_dark":     _CORPORATE_DARK,
    "modern_light":       _MODERN_LIGHT,
    "startup_minimal":    _STARTUP_MINIMAL,
    "healthcare_clinical": _HEALTHCARE_CLINICAL,
    "financial_formal":   _FINANCIAL_FORMAL,
}


def resolve_theme(theme_name: str) -> ThemeTokens:
    """
    Retrieve ThemeTokens for a theme name.
    Falls back to modern_light if theme_name is unrecognised (logs a warning).
    """
    if theme_name not in _THEME_REGISTRY:
        import logging
        logging.getLogger(__name__).warning(
            f"Unknown theme '{theme_name}', using 'modern_light' as fallback."
        )
    return _THEME_REGISTRY.get(theme_name, _MODERN_LIGHT)
