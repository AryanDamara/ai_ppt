"""
Module 14 — Layout Validator with Accessibility Checks
Post-solve algorithmic validation for overlaps, accessibility, and screen reader order.
"""

from typing import List, Dict
from .cassowary_solver import LayoutSolution

# WCAG AA minimum contrast ratio for text
WCAG_AA_MIN_CONTRAST = 4.5

# Minimum touch target size: 44x44 CSS px ≈ 33x33 layout units at 1280px canvas
MIN_TOUCH_TARGET_UNITS = 33


class LayoutValidator:
    """
    Post-solve algorithmic validation.
    Checks: overlaps, font size floors, whitespace balance, accessibility.
    """

    def validate(self, solution: LayoutSolution, slide: dict) -> List[str]:
        warnings = []
        warnings.extend(self._check_overlaps(solution))
        warnings.extend(self._check_min_font_size(solution))
        warnings.extend(self._check_whitespace_balance(solution))
        warnings.extend(self._check_touch_targets(solution, slide))
        warnings.extend(self._check_screen_reader_order(solution, slide))
        warnings.extend(self._check_contrast(solution, slide))
        return warnings

    def _check_overlaps(self, solution: LayoutSolution) -> List[str]:
        warnings = []
        elements = list(solution.elements.items())

        for i, (id_a, elem_a) in enumerate(elements):
            for id_b, elem_b in elements[i+1:]:
                if "footer" in id_a or "footer" in id_b:
                    continue

                a_right = elem_a["x"] + elem_a["width"]
                a_bottom = elem_a["y"] + elem_a["height"]
                b_right = elem_b["x"] + elem_b["width"]
                b_bottom = elem_b["y"] + elem_b["height"]

                if (elem_a["x"] < b_right and a_right > elem_b["x"] and
                        elem_a["y"] < b_bottom and a_bottom > elem_b["y"]):
                    warnings.append(f"Bounding box overlap: {id_a} and {id_b}")

        return warnings

    def _check_min_font_size(self, solution: LayoutSolution) -> List[str]:
        warnings = []
        for elem_id, elem in solution.elements.items():
            font_px = elem.get("font_size_px", 18)
            if font_px < 12:
                warnings.append(f"Font {font_px}px on '{elem_id}' below minimum 12px (accessibility)")
        return warnings

    def _check_whitespace_balance(self, solution: LayoutSolution) -> List[str]:
        content_elements = [
            elem for elem_id, elem in solution.elements.items()
            if "footer" not in elem_id
        ]
        if not content_elements:
            return []

        topmost_y = min(e["y"] for e in content_elements)
        bottommost_bottom = max(e["y"] + e["height"] for e in content_elements)

        top_margin = topmost_y
        bottom_margin = solution.slide_height_units - bottommost_bottom

        if top_margin > 0 and bottom_margin > 0:
            ratio = max(top_margin, bottom_margin) / min(top_margin, bottom_margin)
            if ratio > 4.0:
                return ["Severe whitespace imbalance (top:bottom ratio > 4:1)"]

        return []

    def _check_touch_targets(self, solution: LayoutSolution, slide: dict) -> List[str]:
        """WCAG 2.5.5: Minimum touch target size 44×44 CSS pixels."""
        warnings = []
        interactive_elements = {"chart", "image", "callout"}

        for elem_id, elem in solution.elements.items():
            if any(t in elem_id for t in interactive_elements):
                if elem["width"] < MIN_TOUCH_TARGET_UNITS or elem["height"] < MIN_TOUCH_TARGET_UNITS:
                    warnings.append(
                        f"Element '{elem_id}' ({elem['width']}×{elem['height']} units) "
                        f"may be below 44×44px touch target (WCAG 2.5.5)"
                    )

        return warnings

    def _check_screen_reader_order(self, solution: LayoutSolution, slide: dict) -> List[str]:
        """WCAG 1.3.2: Screen reader order must match visual reading order."""
        warnings = []
        slide_type = slide.get("slide_type", "")

        if slide_type == "content_bullets":
            bullets = slide.get("content", {}).get("bullets", [])
            json_order = [b["element_id"] for b in bullets if "element_id" in b]

            bullet_elements = {
                k: v for k, v in solution.elements.items()
                if k in json_order
            }
            visual_order = sorted(
                bullet_elements.items(),
                key=lambda kv: (kv[1]["y"], kv[1]["x"])
            )
            visual_ids = [k for k, _ in visual_order]

            if visual_ids != json_order:
                warnings.append(
                    "Screen reader order mismatch — visual order differs from DOM order"
                )

        return warnings

    def _check_contrast(self, solution: LayoutSolution, slide: dict) -> List[str]:
        warnings = []
        bg_color = slide.get("template", {}).get("overrides", {}).get("background_color")
        if bg_color:
            warnings.append(
                f"Custom background {bg_color} — verify WCAG AA contrast ratio ≥ 4.5:1"
            )
        return warnings