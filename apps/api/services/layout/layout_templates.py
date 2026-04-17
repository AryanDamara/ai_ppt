"""
Layout Templates — Predefined zone configurations for each slide type.
"""

from dataclasses import dataclass
from typing import Dict, Optional
from enum import Enum


class Zone(str, Enum):
    TITLE = "title"
    BODY = "body"
    BODY_LEFT = "body_left"
    BODY_RIGHT = "body_right"
    IMAGE = "image"
    CHART = "chart"
    TABLE = "table"
    FOOTER = "footer"
    CALL_TO_ACTION = "call_to_action"
    SUBTITLE = "subtitle"


@dataclass
class ZoneBounds:
    x: int
    y: int
    width: int
    height: int
    z_index: int = 200
    text_align: str = "left"
    flex_grow: bool = False


@dataclass
class LayoutTemplate:
    template_id: str
    zones: Dict[Zone, ZoneBounds]
    aspect_ratio: str = "16:9"
    min_font_scale: float = 0.8
    max_font_scale: float = 1.2


# Standard 16:9 slide dimensions
SLIDE_W = 1000
SLIDE_H = 562
SAFE_TOP = 72
SAFE_BOTTOM = 710
SAFE_LEFT = 60
SAFE_RIGHT = 940


# Template definitions
TEMPLATES = {
    "title_slide": LayoutTemplate(
        template_id="title_slide",
        zones={
            Zone.TITLE: ZoneBounds(SAFE_LEFT, 200, 880, 100, z_index=300),
            Zone.SUBTITLE: ZoneBounds(SAFE_LEFT, 320, 880, 80, z_index=200),
            Zone.FOOTER: ZoneBounds(SAFE_LEFT, SAFE_BOTTOM, 880, 40, z_index=100),
        }
    ),

    "section_divider": LayoutTemplate(
        template_id="section_divider",
        zones={
            Zone.TITLE: ZoneBounds(SAFE_LEFT, 250, 880, 80, z_index=300),
            Zone.SUBTITLE: ZoneBounds(SAFE_LEFT, 350, 880, 60, z_index=200),
        }
    ),

    "content_bullets": LayoutTemplate(
        template_id="content_bullets",
        zones={
            Zone.TITLE: ZoneBounds(SAFE_LEFT, SAFE_TOP, 880, 80, z_index=300),
            Zone.BODY: ZoneBounds(SAFE_LEFT, 180, 880, 480, z_index=200, flex_grow=True),
            Zone.FOOTER: ZoneBounds(SAFE_LEFT, SAFE_BOTTOM, 880, 40, z_index=100),
        }
    ),

    "content_bullets_2col": LayoutTemplate(
        template_id="content_bullets_2col",
        zones={
            Zone.TITLE: ZoneBounds(SAFE_LEFT, SAFE_TOP, 880, 80, z_index=300),
            Zone.BODY_LEFT: ZoneBounds(SAFE_LEFT, 180, 430, 480, z_index=200, flex_grow=True),
            Zone.BODY_RIGHT: ZoneBounds(510, 180, 430, 480, z_index=200, flex_grow=True),
            Zone.FOOTER: ZoneBounds(SAFE_LEFT, SAFE_BOTTOM, 880, 40, z_index=100),
        }
    ),

    "visual_split": LayoutTemplate(
        template_id="visual_split",
        zones={
            Zone.TITLE: ZoneBounds(SAFE_LEFT, SAFE_TOP, 880, 80, z_index=300),
            Zone.BODY: ZoneBounds(SAFE_LEFT, 180, 450, 480, z_index=200),
            Zone.IMAGE: ZoneBounds(530, 180, 410, 480, z_index=150),
            Zone.FOOTER: ZoneBounds(SAFE_LEFT, SAFE_BOTTOM, 880, 40, z_index=100),
        }
    ),

    "visual_split_reversed": LayoutTemplate(
        template_id="visual_split_reversed",
        zones={
            Zone.TITLE: ZoneBounds(SAFE_LEFT, SAFE_TOP, 880, 80, z_index=300),
            Zone.BODY: ZoneBounds(530, 180, 410, 480, z_index=200),
            Zone.IMAGE: ZoneBounds(SAFE_LEFT, 180, 450, 480, z_index=150),
            Zone.FOOTER: ZoneBounds(SAFE_LEFT, SAFE_BOTTOM, 880, 40, z_index=100),
        }
    ),

    "full_bleed_image": LayoutTemplate(
        template_id="full_bleed_image",
        zones={
            Zone.TITLE: ZoneBounds(SAFE_LEFT, SAFE_TOP, 880, 60, z_index=400),
            Zone.IMAGE: ZoneBounds(0, 0, SLIDE_W, SLIDE_H, z_index=100),
            Zone.CALL_TO_ACTION: ZoneBounds(SAFE_LEFT, SAFE_BOTTOM - 60, 880, 40, z_index=300),
        }
    ),

    "data_chart": LayoutTemplate(
        template_id="data_chart",
        zones={
            Zone.TITLE: ZoneBounds(SAFE_LEFT, SAFE_TOP, 880, 80, z_index=300),
            Zone.CHART: ZoneBounds(SAFE_LEFT, 180, 880, 400, z_index=200),
            Zone.BODY: ZoneBounds(SAFE_LEFT, 600, 880, 100, z_index=250),
            Zone.FOOTER: ZoneBounds(SAFE_LEFT, SAFE_BOTTOM, 880, 40, z_index=100),
        }
    ),

    "table": LayoutTemplate(
        template_id="table",
        zones={
            Zone.TITLE: ZoneBounds(SAFE_LEFT, SAFE_TOP, 880, 80, z_index=300),
            Zone.TABLE: ZoneBounds(SAFE_LEFT, 180, 880, 400, z_index=200),
            Zone.FOOTER: ZoneBounds(SAFE_LEFT, SAFE_BOTTOM, 880, 40, z_index=100),
        }
    ),
}


def select_template(slide_type: str, layout_variant: str = "default",
                   visual_anchor: str = "none", text_position: str = "left") -> LayoutTemplate:
    """
    Select appropriate template based on slide type and layout hints.

    Args:
        slide_type: Type of slide (content_bullets, visual_split, etc.)
        layout_variant: Sub-variant (single_column, two_column, etc.)
        visual_anchor: Where visuals should gravitate (left, right, center)
        text_position: For visual_split: left/right of image
    """
    if slide_type == "title_slide":
        return TEMPLATES["title_slide"]

    if slide_type == "section_divider":
        return TEMPLATES["section_divider"]

    if slide_type == "content_bullets":
        if layout_variant in ("two_column", "2_col"):
            return TEMPLATES["content_bullets_2col"]
        return TEMPLATES["content_bullets"]

    if slide_type == "visual_split":
        if text_position == "right" or visual_anchor == "left":
            return TEMPLATES["visual_split_reversed"]
        return TEMPLATES["visual_split"]

    if slide_type == "full_bleed_image":
        return TEMPLATES["full_bleed_image"]

    if slide_type in ("data_chart", "chart"):
        return TEMPLATES["data_chart"]

    if slide_type in ("table", "data_table"):
        return TEMPLATES["table"]

    # Default fallback
    return TEMPLATES["content_bullets"]


def get_template_for_slide(slide: dict) -> LayoutTemplate:
    """Extract template parameters from slide JSON."""
    slide_type = slide.get("slide_type", "content_bullets")
    content = slide.get("content", {})
    layout_hints = slide.get("layout_hints", {})

    layout_variant = content.get("layout_variant", "default")
    visual_anchor = layout_hints.get("visual_anchor", "none")
    text_position = content.get("text_position", "left")

    return select_template(slide_type, layout_variant, visual_anchor, text_position)