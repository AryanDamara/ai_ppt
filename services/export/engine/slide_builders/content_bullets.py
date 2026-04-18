"""
content_bullets builder.

Schema fields consumed:
  action_title                      → rendered as slide title (analyst "So What?")
  content.layout_variant            → single_column / two_column / three_column / pyramid
  content.bullets[].element_id      → key into layout_solution.elements
  content.bullets[].text            → bullet text (max 200 chars)
  content.bullets[].indent_level    → 0/1/2 → horizontal indentation
  content.bullets[].emphasis        → none/highlight/bold/critical/subtle
  content.bullets[].supporting_data → smaller stat text below bullet

LayoutSolution zones consumed:
  "title"       → action_title text box
  "body"        → single-column body (or "body_left"/"body_right" for two_column)
  element_ids   → individual bullet text boxes (one per bullet.element_id)

Emphasis styles:
  none      → body_rgb, not bold, not italic
  bold      → body_rgb, bold
  highlight → accent_primary_rgb, not bold
  critical  → danger red (239,68,68), bold
  subtle    → subtitle_rgb, italic
"""
from pptx.slide import Slide
from pptx.enum.text import PP_ALIGN
from .base_builder import BaseSlideBuilder

_EMPHASIS_STYLES: dict[str, dict] = {
    "none":      {"bold": False, "italic": False, "color_key": "body"},
    "bold":      {"bold": True,  "italic": False, "color_key": "body"},
    "highlight": {"bold": False, "italic": False, "color_key": "accent_primary"},
    "critical":  {"bold": True,  "italic": False, "color_key": "danger"},
    "subtle":    {"bold": False, "italic": True,  "color_key": "subtitle"},
}


class ContentBulletsBuilder(BaseSlideBuilder):

    def build(
        self,
        slide: Slide,
        slide_data: dict,
        layout_solution: dict,
        slide_index: int,
        total_slides: int,
    ) -> None:
        self.set_slide_background(slide)

        content    = slide_data.get("content", {})
        bullets    = content.get("bullets", [])
        font_scale = self.get_font_scale(slide_data)
        overrides  = slide_data.get("template", {}).get("overrides", {})
        is_rtl     = self.is_rtl_layout(layout_solution)
        align      = self.get_pptx_alignment("left", is_rtl)

        # ── Title: action_title ───────────────────────────────────────────────
        title_bounds = self.get_element_bounds(layout_solution, "title")
        if title_bounds:
            self.add_textbox(
                slide, title_bounds,
                slide_data.get("action_title", ""),
                font_size_units=title_bounds.get("font_size_units", 48),
                font_scale=font_scale,
                color_rgb=self.tokens.title_rgb,
                bold=True,
                font_name=self.tokens.display_font_name,
                alignment=align,
            )

        # ── Bullets: each positioned by element_id from LayoutSolution ────────
        for bullet in bullets:
            element_id = bullet.get("element_id")
            if not element_id:
                continue

            elem_bounds = self.get_element_bounds(layout_solution, element_id)
            if not elem_bounds:
                # Element missing from layout solution — skip silently
                continue

            emphasis = bullet.get("emphasis", "none")
            style    = _EMPHASIS_STYLES.get(emphasis, _EMPHASIS_STYLES["none"])

            color_rgb = {
                "body":         self.tokens.body_rgb,
                "accent_primary": self.tokens.accent_primary_rgb,
                "danger":       (239, 68, 68),
                "subtitle":     self.tokens.subtitle_rgb,
            }.get(style["color_key"], self.tokens.body_rgb)

            body_font_units = elem_bounds.get("font_size_units", 24)

            paragraphs = [
                {
                    "text":           bullet.get("text", ""),
                    "font_size_units": body_font_units,
                    "bold":           style["bold"],
                    "italic":         style["italic"],
                    "color_rgb":      color_rgb,
                    "font_name":      self.tokens.body_font_name,
                    "indent_level":   bullet.get("indent_level", 0),
                }
            ]

            # supporting_data: smaller italic accent text below the bullet
            supporting = bullet.get("supporting_data", "")
            if supporting:
                paragraphs.append({
                    "text":           supporting,
                    "font_size_units": int(body_font_units * 0.8),
                    "bold":           False,
                    "italic":         True,
                    "color_rgb":      self.tokens.accent_secondary_rgb,
                    "font_name":      self.tokens.body_font_name,
                    "indent_level":   bullet.get("indent_level", 0),
                })

            self.add_textbox_multiline(
                slide, elem_bounds, paragraphs,
                font_scale=font_scale,
                alignment=align,
            )

        self.add_footer(
            slide,
            source_footer=slide_data.get("source_footer"),
            slide_index=slide_index,
            total_slides=total_slides,
            hide_footer=overrides.get("hide_footer", False),
            hide_slide_number=overrides.get("hide_slide_number", False),
        )
