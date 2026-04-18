"""
title_slide builder.

IMPORTANT: action_title is NOT rendered on title slides.
  action_title = analyst "So What?" (max 60 chars) — internal use only
  content.headline = audience-facing title displayed on slide — USE THIS

Schema fields consumed:
  content.headline             → large centered display title
  content.subheadline          → secondary text below headline
  content.presenter_name       → name of presenter
  content.presenter_title      → role/title of presenter
  content.date                 → presentation date (ISO format "YYYY-MM-DD")
  content.event_name           → conference or meeting name

LayoutSolution zones consumed:
  "title"     → content.headline text box
  "subtitle"  → content.subheadline text box
  "presenter" → combined presenter_name · presenter_title · date · event_name
"""
from pptx.slide import Slide
from pptx.enum.text import PP_ALIGN
from .base_builder import BaseSlideBuilder


class TitleSlideBuilder(BaseSlideBuilder):

    def build(
        self,
        slide: Slide,
        slide_data: dict,
        layout_solution: dict,
        slide_index: int,
        total_slides: int,
    ) -> None:
        self.set_slide_background(slide)

        content   = slide_data.get("content", {})
        font_scale = self.get_font_scale(slide_data)
        overrides  = slide_data.get("template", {}).get("overrides", {})
        is_rtl     = self.is_rtl_layout(layout_solution)
        align      = PP_ALIGN.RIGHT if is_rtl else PP_ALIGN.CENTER

        # ── Headline (content.headline, NOT action_title) ────────────────────
        headline      = content.get("headline", "")
        title_bounds  = self.get_element_bounds(layout_solution, "title")
        if headline and title_bounds:
            self.add_textbox(
                slide, title_bounds, headline,
                font_size_units=title_bounds.get("font_size_units", 64),
                font_scale=font_scale,
                color_rgb=self.tokens.title_rgb,
                bold=True,
                font_name=self.tokens.display_font_name,
                alignment=align,
            )

        # ── Subheadline ───────────────────────────────────────────────────────
        subheadline      = content.get("subheadline", "")
        subtitle_bounds  = self.get_element_bounds(layout_solution, "subtitle")
        if subheadline and subtitle_bounds:
            self.add_textbox(
                slide, subtitle_bounds, subheadline,
                font_size_units=subtitle_bounds.get("font_size_units", 36),
                font_scale=font_scale,
                color_rgb=self.tokens.subtitle_rgb,
                font_name=self.tokens.body_font_name,
                alignment=align,
            )

        # ── Presenter block: name · title · date · event ─────────────────────
        parts = [p for p in [
            content.get("presenter_name", ""),
            content.get("presenter_title", ""),
            content.get("date", ""),
            content.get("event_name", ""),
        ] if p]
        presenter_text    = "  ·  ".join(parts)
        presenter_bounds  = self.get_element_bounds(layout_solution, "presenter")
        if presenter_text and presenter_bounds:
            self.add_textbox(
                slide, presenter_bounds, presenter_text,
                font_size_units=presenter_bounds.get("font_size_units", 20),
                font_scale=font_scale,
                color_rgb=self.tokens.footer_rgb,
                font_name=self.tokens.body_font_name,
                alignment=align,
            )

        # Title slides default to hiding footer + slide number
        self.add_footer(
            slide,
            source_footer=slide_data.get("source_footer"),
            slide_index=slide_index,
            total_slides=total_slides,
            hide_footer=overrides.get("hide_footer", True),
            hide_slide_number=overrides.get("hide_slide_number", True),
        )
