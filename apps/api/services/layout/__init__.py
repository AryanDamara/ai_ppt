"""
Layout Engine v2.0 — CSP-based slide layout solver.
"""

from .layout_engine import LayoutEngine
from .cassowary_solver import CassowarySlideSolver, LayoutSolution
from .unit_converter import units_to_emu, units_to_css_px, get_slide_metrics
from .font_cache import get_theme_fonts, preload_all_fonts
from .i18n_profiles import get_profile, TypographyProfile

__all__ = [
    "LayoutEngine",
    "CassowarySlideSolver",
    "LayoutSolution",
    "units_to_emu",
    "units_to_css_px",
    "get_slide_metrics",
    "get_theme_fonts",
    "preload_all_fonts",
    "get_profile",
    "TypographyProfile",
]