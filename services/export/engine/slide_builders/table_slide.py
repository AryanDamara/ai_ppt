"""
table_slide builder.
Delegates table rendering to TableBuilder for clean separation.
"""
from pptx.slide import Slide
from pptx.enum.text import PP_ALIGN
from .base_builder import BaseSlideBuilder
from engine.table_builder import TableBuilder


class TableSlideBuilder(BaseSlideBuilder):

    def __init__(self, tokens, aspect_ratio="16:9"):
        super().__init__(tokens, aspect_ratio)
        self._table_builder = TableBuilder(tokens, aspect_ratio)

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

        body_bounds = self.get_element_bounds(layout_solution, "body")
        if body_bounds:
            self._table_builder.build_table(
                slide=slide,
                headers=content.get("headers", []),
                rows=content.get("rows", []),
                bounds=body_bounds,
                highlight_cells=content.get("highlight_cells", []),
                font_scale=font_scale,
            )

        source = slide_data.get("source_footer") or content.get("source_citation", "")
        self.add_footer(
            slide,
            source_footer=source,
            slide_index=slide_index,
            total_slides=total_slides,
            hide_footer=overrides.get("hide_footer", False),
            hide_slide_number=overrides.get("hide_slide_number", False),
        )
