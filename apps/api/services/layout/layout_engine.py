"""
Layout Engine — Main entry point for slide layout solving.
Orchestrates constraint solving, relaxation, and validation.
"""

from typing import List, Dict, Optional
import time

from .cassowary_solver import CassowarySlideSolver, LayoutSolution
from .layout_templates import LayoutTemplate, get_template_for_slide
from .i18n_profiles import get_profile, TypographyProfile
from .font_cache import get_theme_fonts, FontMetrics
from .relaxation import RelaxationResult, apply_relaxation_result, build_continuation_slide, reconcile_slide_indices
from .layout_validator import LayoutValidator
from .layout_telemetry import LayoutTelemetry, record_solve


class LayoutEngine:
    """Main layout engine that coordinates all layout operations."""

    def __init__(self):
        self._solver = CassowarySlideSolver()
        self._validator = LayoutValidator()

    def solve_slide(
        self,
        slide: dict,
        theme: str = "modern_light",
        language: str = "en",
        canvas_px_w: int = 1280,
        canvas_px_h: int = 720,
    ) -> LayoutSolution:
        """
        Solve layout for a single slide.

        Args:
            slide: Slide JSON from Phase 1
            theme: Theme identifier for font selection
            language: Language code for typography profile
            canvas_px_w: Canvas width in CSS pixels
            canvas_px_h: Canvas height in CSS pixels

        Returns:
            LayoutSolution with computed element positions
        """
        template = get_template_for_slide(slide)
        profile = get_profile(language)
        fonts = get_theme_fonts(theme, language)

        return self._solver.solve(
            slide=slide,
            template=template,
            profile=profile,
            body_font=fonts["body"],
            display_font=fonts["display"],
            canvas_px_w=canvas_px_w,
            canvas_px_h=canvas_px_h,
        )

    def solve_deck(
        self,
        slides: List[dict],
        theme: str = "modern_light",
        language: str = "en",
        canvas_px_w: int = 1280,
        canvas_px_h: int = 720,
    ) -> List[LayoutSolution]:
        """
        Solve layouts for an entire deck, handling continuation slides.

        Args:
            slides: List of slide JSON objects
            theme: Theme identifier
            language: Language code
            canvas_px_w: Canvas width in CSS pixels
            canvas_px_h: Canvas height in CSS pixels

        Returns:
            List of LayoutSolution objects (may be more than input slides due to continuations)
        """
        results = []
        all_slides = list(slides)  # Copy for potential modification

        for slide in slides:
            solution = self.solve_slide(slide, theme, language, canvas_px_w, canvas_px_h)
            results.append(solution)

            # Handle continuation slides for overflow content
            if solution.requires_continuation_slide and solution.continuation_bullets:
                continuation = build_continuation_slide(slide, solution.continuation_bullets)
                all_slides.append(continuation)

                cont_solution = self.solve_slide(continuation, theme, language, canvas_px_w, canvas_px_h)
                results.append(cont_solution)

        return results

    def validate_solution(self, solution: LayoutSolution, slide: dict) -> List[str]:
        """Run post-solve validation on a layout solution."""
        return self._validator.validate(solution, slide)


def solve_slide_with_relaxation(
    slide: dict,
    theme: str = "modern_light",
    language: str = "en",
    canvas_px_w: int = 1280,
    canvas_px_h: int = 720,
) -> tuple[LayoutSolution, dict]:
    """
    Solve a slide and apply relaxation results to the slide JSON.

    Returns:
        (LayoutSolution, updated_slide_dict)
    """
    engine = LayoutEngine()
    solution = engine.solve_slide(slide, theme, language, canvas_px_w, canvas_px_h)

    result = RelaxationResult(
        solution=solution,
        font_scale_to_write=solution.font_scale_override,
        layout_warnings_to_write=solution.layout_warnings,
    )

    updated_slide = apply_relaxation_result(slide, result)
    return solution, updated_slide