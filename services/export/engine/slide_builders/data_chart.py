"""
data_chart builder.

Schema fields consumed:
  action_title                        → slide title
  content.chart_type                  → one of 8 valid values
  content.chart_data.series           → [{name, values, color?, unit?}]
  content.chart_data.categories       → string labels (length must match values)
  content.chart_data.global_unit      → number format string
  content.chart_data.data_source      → shown in footer
  content.chart_options.show_legend   → bool
  content.chart_options.show_data_labels → bool
  content.chart_options.y_axis_max    → optional float
  content.chart_options.y_axis_min    → optional float
  content.chart_options.trendline_enabled → bool
  content.key_takeaway_callout        → callout text below chart

LayoutSolution zones consumed:
  "title"   → action_title
  "chart"   → native chart bounding box
  "callout" → key_takeaway_callout text
"""
from pptx.slide import Slide
from pptx.enum.text import PP_ALIGN
from .base_builder import BaseSlideBuilder
from engine.chart_engine import ChartEngine


class DataChartBuilder(BaseSlideBuilder):

    def __init__(self, tokens, aspect_ratio="16:9"):
        super().__init__(tokens, aspect_ratio)
        self._chart_engine = ChartEngine(tokens)

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

        # ── Title ─────────────────────────────────────────────────────────────
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

        # ── Native Office chart ───────────────────────────────────────────────
        chart_bounds = self.get_element_bounds(layout_solution, "chart")
        if chart_bounds:
            self._chart_engine.add_chart(
                slide=slide,
                chart_type=content.get("chart_type", "column_clustered"),
                chart_data=content.get("chart_data", {}),
                chart_options=content.get("chart_options", {}),
                bounds=chart_bounds,
                aspect_ratio=self.aspect_ratio,
            )

        # ── Key takeaway callout ──────────────────────────────────────────────
        callout_text   = content.get("key_takeaway_callout", "")
        callout_bounds = self.get_element_bounds(layout_solution, "callout")
        if callout_text and callout_bounds:
            self.add_textbox(
                slide, callout_bounds, callout_text,
                font_size_units=callout_bounds.get("font_size_units", 20),
                font_scale=font_scale,
                color_rgb=self.tokens.accent_primary_rgb,
                bold=True,
                italic=True,
                font_name=self.tokens.body_font_name,
                alignment=PP_ALIGN.CENTER,
            )

        # Data source shown in footer (prefers source_footer, falls back to data_source)
        source = slide_data.get("source_footer") or \
                 content.get("chart_data", {}).get("data_source", "")

        self.add_footer(
            slide,
            source_footer=source,
            slide_index=slide_index,
            total_slides=total_slides,
            hide_footer=overrides.get("hide_footer", False),
            hide_slide_number=overrides.get("hide_slide_number", False),
        )
