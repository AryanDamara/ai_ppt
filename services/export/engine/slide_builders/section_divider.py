"""
section_divider builder.

Schema fields consumed:
  content.section_title     → large display text (required, max 5 words)
  content.section_number    → optional "01" string
  content.transition_quote  → optional pull quote (used if no preview_bullets)
  content.preview_bullets   → optional list[str] max 3 items

LayoutSolution zones consumed:
  "section_number"  → optional number zone
  "section_title"   → large title zone
  "preview"         → preview bullets or transition quote
"""
from pptx.slide import Slide
from pptx.enum.text import PP_ALIGN
from .base_builder import BaseSlideBuilder


class SectionDividerBuilder(BaseSlideBuilder):

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
        font_scale = self.get_font_scale(slide_data)
        overrides  = slide_data.get("template", {}).get("overrides", {})
        is_rtl     = self.is_rtl_layout(layout_solution)
        align      = self.get_pptx_alignment("left", is_rtl)

        # Section number ("01")
        num_bounds      = self.get_element_bounds(layout_solution, "section_number")
        section_number  = content.get("section_number", "")
        if section_number and num_bounds:
            self.add_textbox(
                slide, num_bounds, section_number,
                font_size_units=num_bounds.get("font_size_units", 28),
                font_scale=font_scale,
                color_rgb=self.tokens.section_number_rgb,
                font_name=self.tokens.body_font_name,
                alignment=align,
            )

        # Section title — the dominant visual element
        title_bounds  = self.get_element_bounds(layout_solution, "section_title")
        section_title = content.get("section_title", "")
        if section_title and title_bounds:
            self.add_textbox(
                slide, title_bounds, section_title,
                font_size_units=title_bounds.get("font_size_units", 72),
                font_scale=font_scale,
                color_rgb=self.tokens.section_title_rgb,
                bold=True,
                font_name=self.tokens.display_font_name,
                alignment=align,
            )

        preview_bounds   = self.get_element_bounds(layout_solution, "preview")
        preview_bullets  = content.get("preview_bullets", [])
        transition_quote = content.get("transition_quote", "")

        if preview_bullets and preview_bounds:
            paragraphs = [
                {
                    "text":           f"  ›  {bullet}",
                    "font_size_units": preview_bounds.get("font_size_units", 20),
                    "bold":           False,
                    "italic":         False,
                    "color_rgb":      self.tokens.subtitle_rgb,
                    "font_name":      self.tokens.body_font_name,
                    "space_after_pt": 4.0,
                }
                for bullet in preview_bullets[:3]
            ]
            self.add_textbox_multiline(
                slide, preview_bounds, paragraphs,
                font_scale=font_scale, alignment=align,
            )

        elif transition_quote and preview_bounds:
            self.add_textbox(
                slide, preview_bounds,
                f'"{transition_quote}"',
                font_size_units=preview_bounds.get("font_size_units", 24),
                font_scale=font_scale,
                color_rgb=self.tokens.subtitle_rgb,
                italic=True,
                font_name=self.tokens.body_font_name,
                alignment=align,
            )

        # Section dividers default to hiding the footer zone
        self.add_footer(
            slide,
            source_footer=None,
            slide_index=slide_index,
            total_slides=total_slides,
            hide_footer=overrides.get("hide_footer", True),
            hide_slide_number=overrides.get("hide_slide_number", True),
        )
