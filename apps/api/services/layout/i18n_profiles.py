"""
Module 4 — i18n Typography Profiles (BiDi-Aware)
Script-specific typography settings with RTL support and non-mirrored elements.
"""

from dataclasses import dataclass, field
from typing import Set, Optional


# Elements that NEVER flip in RTL layouts even when mirror_horizontal=True
NEVER_MIRROR_ELEMENT_TYPES = frozenset({
    "chart", "image", "video",
})

# Icons that should NOT flip in RTL (universal/non-directional)
NON_DIRECTIONAL_ICONS = frozenset({
    "search", "settings", "home", "user", "mail", "bell",
    "star", "heart", "share", "download", "upload", "close",
    "plus", "minus", "check", "info", "warning", "error",
})

# Icons that SHOULD flip in RTL (directional)
DIRECTIONAL_ICONS = frozenset({
    "arrow_left", "arrow_right", "chevron_left", "chevron_right",
    "forward", "back", "next", "previous", "undo", "redo",
})


@dataclass
class TypographyProfile:
    script: str
    line_height_multiplier: float
    title_to_body_ratio: float
    min_body_font_size_px: float
    max_body_font_size_px: float
    optimal_chars_per_line: int
    baseline_grid_units: int
    rtl: bool
    mirror_horizontal: bool
    break_at_any_char: bool
    supports_italic: bool
    margin_top: int
    margin_bottom: int
    margin_left: int
    margin_right: int
    min_element_gap: int
    ltr_exempt_types: Set[str] = field(default_factory=lambda: set(NEVER_MIRROR_ELEMENT_TYPES))

    def should_mirror_element(self, element_type: str, icon_name: Optional[str] = None) -> bool:
        """
        Determines if an element should have its x-coordinate mirrored in RTL layouts.
        """
        if not self.mirror_horizontal:
            return False

        if element_type in self.ltr_exempt_types:
            return False

        if element_type == "icon" and icon_name:
            if icon_name in NON_DIRECTIONAL_ICONS:
                return False
            if icon_name in DIRECTIONAL_ICONS:
                return True

        return True

    def flip_visual_anchor(self, anchor: str) -> str:
        """Mirror layout_hints.visual_anchor for RTL layouts."""
        if not self.mirror_horizontal:
            return anchor
        return {"left": "right", "right": "left"}.get(anchor, anchor)

    def flip_x_coordinate(self, x: float, width: float, slide_width: int = 1000) -> float:
        """Convert an LTR x-coordinate to its RTL equivalent."""
        if not self.mirror_horizontal:
            return x
        return slide_width - x - width

    def text_align(self) -> str:
        """Primary text alignment for this script."""
        return "right" if self.rtl else "left"

    def get_bidi_override(self) -> str:
        """
        BiDi Unicode control character to prepend to mixed-direction text.
        """
        if self.rtl:
            return "\u2067"   # RIGHT-TO-LEFT ISOLATE
        return "\u2066"        # LEFT-TO-RIGHT ISOLATE


LATIN = TypographyProfile(
    script="latin", line_height_multiplier=1.2, title_to_body_ratio=1.8,
    min_body_font_size_px=18.0, max_body_font_size_px=28.0, optimal_chars_per_line=65,
    baseline_grid_units=8, rtl=False, mirror_horizontal=False, break_at_any_char=False,
    supports_italic=True, margin_top=72, margin_bottom=40, margin_left=60, margin_right=60, min_element_gap=16,
)

CJK = TypographyProfile(
    script="cjk", line_height_multiplier=1.75, title_to_body_ratio=1.6,
    min_body_font_size_px=16.0, max_body_font_size_px=24.0, optimal_chars_per_line=35,
    baseline_grid_units=8, rtl=False, mirror_horizontal=False, break_at_any_char=True,
    supports_italic=False, margin_top=72, margin_bottom=40, margin_left=60, margin_right=60, min_element_gap=16,
)

RTL = TypographyProfile(
    script="rtl", line_height_multiplier=1.4, title_to_body_ratio=1.8,
    min_body_font_size_px=18.0, max_body_font_size_px=28.0, optimal_chars_per_line=50,
    baseline_grid_units=8, rtl=True, mirror_horizontal=True, break_at_any_char=False,
    supports_italic=False, margin_top=72, margin_bottom=40, margin_left=60, margin_right=60, min_element_gap=16,
    ltr_exempt_types=NEVER_MIRROR_ELEMENT_TYPES,
)

PROFILE_MAP = {
    "en": LATIN, "en-US": LATIN, "en-GB": LATIN, "fr": LATIN, "de": LATIN,
    "es": LATIN, "it": LATIN, "pt": LATIN, "nl": LATIN, "pl": LATIN,
    "zh": CJK, "zh-CN": CJK, "zh-TW": CJK, "ja": CJK, "ko": CJK,
    "ar": RTL, "he": RTL, "fa": RTL, "ur": RTL,
}

DEFAULT_PROFILE = LATIN


def get_profile(language: str) -> TypographyProfile:
    if language in PROFILE_MAP:
        return PROFILE_MAP[language]
    prefix = language.split("-")[0]
    if prefix in PROFILE_MAP:
        return PROFILE_MAP[prefix]
    return DEFAULT_PROFILE