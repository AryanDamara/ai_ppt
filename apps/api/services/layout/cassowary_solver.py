"""
Module 5 — Cassowary Solver (Symbolic Weights + Pre-Validation)
CSP-based layout solver with 4-tier relaxation.
"""

from cassowary import SimplexSolver, Variable, STRONG, REQUIRED, WEAK, MEDIUM
from cassowary.expression import Expression
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Tuple
import time

from .layout_templates import LayoutTemplate, ZoneBounds, Zone, get_template_for_slide
from .i18n_profiles import TypographyProfile
from .font_metrics import FontMetrics, TextMeasurer
from .unit_converter import units_to_css_px, DEFAULT_METRICS, get_slide_metrics
from .constraint_validator import preflight_check, PreflightResult
from .layout_telemetry import LayoutTelemetry, record_solve


@dataclass
class ElementVariables:
    element_id: str
    x: Variable
    y: Variable
    width: Variable
    height: Variable
    font_size: Variable

    @property
    def right(self) -> Expression:
        return self.x + self.width

    @property
    def bottom(self) -> Expression:
        return self.y + self.height


@dataclass
class LayoutSolution:
    slide_id: str
    relaxation_tier: int
    solve_time_ms: float
    warnings: List[str]
    elements: Dict[str, Dict]
    slide_width_units: int = 1000
    slide_height_units: int = 562
    font_scale_override: Optional[float] = None
    layout_warnings: List[str] = field(default_factory=list)
    requires_continuation_slide: bool = False
    continuation_bullets: List[dict] = field(default_factory=list)


class CassowarySlideSolver:
    SLIDE_W = 1000
    SLIDE_H = 562

    def __init__(self):
        self._measurer = TextMeasurer()

    def solve(
        self,
        slide: dict,
        template: LayoutTemplate,
        profile: TypographyProfile,
        body_font: FontMetrics,
        display_font: FontMetrics,
        canvas_px_w: int = 1280,
        canvas_px_h: int = 720,
    ) -> LayoutSolution:
        start = time.perf_counter()

        # Module 0: Pre-flight validation
        available_fonts = list(body_font.advance_width_cache.keys())
        preflight = preflight_check(
            slide=slide,
            template_zones={z.value: {"x": b.x, "y": b.y, "width": b.width, "height": b.height}
                           for z, b in template.zones.items()},
            slide_w=self.SLIDE_W,
            slide_h=self.SLIDE_H,
            canvas_px_w=canvas_px_w,
            canvas_px_h=canvas_px_h,
            available_font_paths=[body_font.family_name],
            required_font_paths=[body_font.family_name],
        )

        bidi_detected = preflight.bidi_detected

        if not preflight.canvas_valid:
            return self._emergency_layout(slide, template, "Invalid canvas dimensions", 0.0)

        # 4-tier relaxation loop
        for tier in range(1, 5):
            try:
                solution = self._attempt_solve(
                    slide, template, profile, body_font, display_font,
                    canvas_px_w, canvas_px_h, tier, bidi_detected
                )
                solution.solve_time_ms = (time.perf_counter() - start) * 1000
                solution.relaxation_tier = tier

                # Record telemetry
                record_solve(LayoutTelemetry(
                    slide_id=slide.get("slide_id", "unknown"),
                    solve_time_ms=solution.solve_time_ms,
                    relaxation_tier=tier,
                    constraint_count=len(template.zones) * 4,
                ))

                return solution
            except Exception:
                if tier == 4:
                    elapsed = time.perf_counter() - start
                    return self._emergency_layout(slide, template, "All tiers exhausted", elapsed)
                continue

        return self._emergency_layout(slide, template, "Solver failed", 0.0)

    def _attempt_solve(
        self,
        slide: dict,
        template: LayoutTemplate,
        profile: TypographyProfile,
        body_font: FontMetrics,
        display_font: FontMetrics,
        canvas_px_w: int,
        canvas_px_h: int,
        tier: int,
        bidi_detected: bool = False,
    ) -> LayoutSolution:
        solver = SimplexSolver()
        element_vars: Dict[str, ElementVariables] = {}
        warnings: List[str] = []

        slide_id = slide.get("slide_id", "unknown")
        slide_type = slide.get("slide_type", "content_bullets")
        content = slide.get("content", {})
        layout_hints = slide.get("layout_hints", {})

        min_font_px = profile.min_body_font_size_px
        if tier >= 2:
            min_font_px = max(14.0, min_font_px - 4.0)

        target_font_px = self._calculate_target_font_size(content, slide_type, profile)
        target_font_px = max(min_font_px, min(target_font_px, profile.max_body_font_size_px))

        body_font_units = int((target_font_px / canvas_px_h) * self.SLIDE_H)
        title_font_units = int(body_font_units * profile.title_to_body_ratio)

        # Create variables for each zone
        for zone, bounds in template.zones.items():
            elem_id = zone.value

            # RTL: flip x coordinates for mirrored elements
            effective_x = bounds.x
            if profile.should_mirror_element(elem_id):
                effective_x = profile.flip_x_coordinate(bounds.x, bounds.width, self.SLIDE_W)

            ev = ElementVariables(
                element_id=elem_id,
                x=Variable(f"{elem_id}_x"),
                y=Variable(f"{elem_id}_y"),
                width=Variable(f"{elem_id}_w"),
                height=Variable(f"{elem_id}_h"),
                font_size=Variable(f"{elem_id}_fs"),
            )
            element_vars[elem_id] = ev

            # CRITICAL FIX: add_edit_var requires strength parameter
            solver.add_edit_var(ev.x, WEAK)
            solver.add_edit_var(ev.y, WEAK)
            solver.add_edit_var(ev.width, WEAK)
            solver.add_edit_var(ev.height, WEAK)

            solver.begin_edit()
            solver.suggest_value(ev.x, effective_x)
            solver.suggest_value(ev.y, bounds.y)
            solver.suggest_value(ev.width, bounds.width)
            solver.suggest_value(ev.height, bounds.height)
            solver.end_edit()

        # Add constraints in priority order: REQUIRED → STRONG → MEDIUM → WEAK
        self._add_required_constraints(solver, element_vars, slide_type, profile)
        self._add_strong_constraints(solver, element_vars, slide, template, profile,
                                     body_font, display_font, body_font_units, title_font_units,
                                     canvas_px_w, canvas_px_h, bidi_detected)
        self._add_medium_constraints(solver, element_vars, layout_hints, profile)
        self._add_weak_constraints(solver, element_vars, layout_hints, profile)

        solver.resolve()

        elements = {}
        for elem_id, ev in element_vars.items():
            x = round(ev.x.value)
            y = round(ev.y.value)
            w = max(20, round(ev.width.value))
            h = max(10, round(ev.height.value))
            x = max(0, min(x, self.SLIDE_W - w))
            y = max(0, min(y, self.SLIDE_H - h))

            zone_enum = Zone(elem_id) if elem_id in [z.value for z in Zone] else None
            zone_config = template.zones.get(zone_enum) if zone_enum else None

            elements[elem_id] = {
                "x": x, "y": y, "width": w, "height": h,
                "font_size_units": body_font_units if elem_id != "title" else title_font_units,
                "font_size_px": round((body_font_units / self.SLIDE_H) * canvas_px_h),
                "z_index": zone_config.z_index if zone_config else 200,
                "text_align": profile.text_align() if zone_config and zone_config.text_align == "left" else
                              (zone_config.text_align if zone_config else "left"),
            }

        # Layout individual content elements (bullets, etc.)
        content_elements = self._layout_content_elements(
            content, slide_type, elements, body_font_units, profile, canvas_px_h
        )
        elements.update(content_elements)

        # Tier 2: record font_scale_override
        font_scale = None
        if tier == 2:
            original = self._calculate_target_font_size(content, slide_type, profile)
            if original > 0:
                raw_scale = target_font_px / original
                font_scale = round(max(0.8, min(1.2, raw_scale)), 3)
            warnings.append(f"Font size reduced to fit content (scale: {font_scale})")

        return LayoutSolution(
            slide_id=slide_id,
            relaxation_tier=tier,
            solve_time_ms=0.0,
            warnings=warnings,
            elements=elements,
            font_scale_override=font_scale,
            layout_warnings=warnings,
        )

    def _add_required_constraints(
        self,
        solver: SimplexSolver,
        evars: Dict[str, ElementVariables],
        slide_type: str,
        profile: TypographyProfile,
    ) -> None:
        """REQUIRED — never relaxed, must always be satisfied."""
        if "title" in evars:
            t = evars["title"]
            solver.add_constraint(t.y >= profile.margin_top, REQUIRED)
            solver.add_constraint(t.x >= profile.margin_left, REQUIRED)
            solver.add_constraint(t.right <= self.SLIDE_W - profile.margin_right, REQUIRED)

        if "title" in evars and "body" in evars:
            solver.add_constraint(
                evars["body"].y >= evars["title"].bottom + profile.min_element_gap,
                REQUIRED
            )

        for elem_id, ev in evars.items():
            if elem_id != "footer":
                solver.add_constraint(ev.bottom <= 710, REQUIRED)

        if "image" in evars:
            solver.add_constraint(evars["image"].width <= self.SLIDE_W * 0.45, REQUIRED)

        for ev in evars.values():
            solver.add_constraint(ev.width >= 20, REQUIRED)
            solver.add_constraint(ev.height >= 10, REQUIRED)

    def _add_strong_constraints(
        self,
        solver: SimplexSolver,
        evars: Dict[str, ElementVariables],
        slide: dict,
        template: LayoutTemplate,
        profile: TypographyProfile,
        body_font: FontMetrics,
        display_font: FontMetrics,
        body_font_units: int,
        title_font_units: int,
        canvas_px_w: int,
        canvas_px_h: int,
        bidi_detected: bool,
    ) -> None:
        """STRONG — text measurement constraints."""
        content = slide.get("content", {})
        slide_type = slide.get("slide_type", "content_bullets")

        body_font_px = (body_font_units / self.SLIDE_H) * canvas_px_h
        title_font_px = (title_font_units / self.SLIDE_H) * canvas_px_h

        action_title = slide.get("action_title", "")
        if action_title and "title" in evars:
            zone_w = evars["title"].width.value
            zone_w_px = units_to_css_px(zone_w, 'width', DEFAULT_METRICS)
            script = "rtl" if profile.rtl else ("cjk" if profile.script == "cjk" else "latin")
            _, title_h_px = self._measurer.measure(
                action_title, display_font, title_font_px, zone_w_px,
                profile.line_height_multiplier, script, bidi_detected,
            )
            title_h_units = (title_h_px / canvas_px_h) * self.SLIDE_H
            solver.add_constraint(evars["title"].height >= title_h_units + 10, STRONG)

        if slide_type == "content_bullets":
            bullets = content.get("bullets", [])
            body_zone = evars.get("body") or evars.get("body_left")
            if body_zone and bullets:
                zone_w_px = units_to_css_px(body_zone.width.value, 'width', DEFAULT_METRICS)
                total_bullet_h = 0.0
                for bullet in bullets:
                    script = "rtl" if profile.rtl else "latin"
                    _, bh = self._measurer.measure(
                        bullet.get("text", ""), body_font, body_font_px, zone_w_px,
                        profile.line_height_multiplier, script, bidi_detected,
                    )
                    total_bullet_h += bh + 12

                total_h_units = (total_bullet_h / canvas_px_h) * self.SLIDE_H
                solver.add_constraint(body_zone.height >= total_h_units + 20, STRONG)

    def _add_medium_constraints(
        self,
        solver: SimplexSolver,
        evars: Dict[str, ElementVariables],
        layout_hints: dict,
        profile: TypographyProfile,
    ) -> None:
        """MEDIUM — spacing and proportion preferences."""
        if "title" in evars and "body" in evars:
            ratio = profile.title_to_body_ratio
            solver.add_constraint(
                evars["title"].height == evars["body"].height * (ratio / 3),
                MEDIUM
            )

    def _add_weak_constraints(
        self,
        solver: SimplexSolver,
        evars: Dict[str, ElementVariables],
        layout_hints: dict,
        profile: TypographyProfile,
    ) -> None:
        """WEAK — aesthetic preferences from layout_hints."""
        priority = layout_hints.get("priority", "balanced")
        density = layout_hints.get("density", "standard")
        visual_anchor = layout_hints.get("visual_anchor", "none")

        gap = {"minimal": 48, "standard": 24, "dense": 8}.get(density, 24)

        if "title" in evars and "body" in evars:
            solver.add_constraint(
                evars["body"].y >= evars["title"].bottom + gap, WEAK
            )

        if priority == "text_primary" and "image" in evars:
            solver.add_constraint(evars["image"].width <= self.SLIDE_W * 0.35, MEDIUM)
        elif priority == "visual_primary" and "body" in evars:
            solver.add_constraint(evars["body"].height <= 200, MEDIUM)

        effective_anchor = profile.flip_visual_anchor(visual_anchor)
        if effective_anchor == "left" and "image" in evars:
            solver.add_constraint(evars["image"].x == 0, WEAK)
        elif effective_anchor == "right" and "image" in evars:
            solver.add_constraint(evars["image"].right == self.SLIDE_W, WEAK)

    def _calculate_target_font_size(self, content: dict, slide_type: str, profile: TypographyProfile) -> float:
        if slide_type == "content_bullets":
            bullets = content.get("bullets", [])
            total_chars = sum(len(b.get("text", "")) for b in bullets)
            density_ratio = min(1.0, total_chars / 400)
            return (profile.max_body_font_size_px -
                    density_ratio * (profile.max_body_font_size_px - profile.min_body_font_size_px))
        elif slide_type in ("section_divider", "title_slide"):
            return profile.max_body_font_size_px
        return (profile.min_body_font_size_px + profile.max_body_font_size_px) / 2

    def _layout_content_elements(
        self,
        content: dict,
        slide_type: str,
        zone_elements: dict,
        body_font_units: int,
        profile: TypographyProfile,
        canvas_px_h: int,
    ) -> dict:
        result = {}

        if slide_type == "content_bullets":
            bullets = content.get("bullets", [])
            body_zone = zone_elements.get("body") or zone_elements.get("body_left")
            if not body_zone or not bullets:
                return result

            y_cursor = body_zone["y"]
            bullet_height = int(body_font_units * profile.line_height_multiplier * 2)
            gap = 12

            for bullet in bullets:
                element_id = bullet.get("element_id")
                if not element_id:
                    continue

                indent = (bullet.get("indent_level", 0)) * 30

                result[element_id] = {
                    "x": body_zone["x"] + indent,
                    "y": y_cursor,
                    "width": body_zone["width"] - indent,
                    "height": bullet_height,
                    "font_size_units": body_font_units,
                    "font_size_px": int((body_font_units / self.SLIDE_H) * canvas_px_h),
                    "z_index": 200,
                    "text_align": profile.text_align(),
                }
                y_cursor += bullet_height + gap

        return result

    def _emergency_layout(self, slide: dict, template: LayoutTemplate, error: str, elapsed: float) -> LayoutSolution:
        elements = {}
        for zone, bounds in template.zones.items():
            elements[zone.value] = {
                "x": bounds.x, "y": bounds.y, "width": bounds.width, "height": bounds.height,
                "font_size_units": 24, "font_size_px": 18,
                "z_index": bounds.z_index, "text_align": bounds.text_align,
            }
        return LayoutSolution(
            slide_id=slide.get("slide_id", "unknown"),
            relaxation_tier=4,
            solve_time_ms=elapsed * 1000,
            warnings=[f"Emergency layout: {error}"],
            elements=elements,
            layout_warnings=["text_overflow_risk"],
        )