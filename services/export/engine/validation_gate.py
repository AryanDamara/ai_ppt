"""
Pre-export validation gate.

Every check here corresponds to a failure mode that would produce a silently
broken PPTX (corrupt chart, missing table, mismatched coordinates). The gate
catches all of them before any python-pptx code runs.
"""
from typing import Tuple

# Valid enum values from the Phase 1 JSON schema
VALID_SLIDE_TYPES = frozenset({
    "title_slide", "content_bullets", "data_chart",
    "visual_split", "table", "section_divider",
})

VALID_THEMES = frozenset({
    "corporate_dark", "modern_light", "startup_minimal",
    "healthcare_clinical", "financial_formal",
})

VALID_CHART_TYPES = frozenset({
    "column_clustered", "column_stacked", "line", "pie",
    "bar", "area", "waterfall", "scatter",
})

VALID_ASPECT_RATIOS = frozenset({"16:9", "4:3"})


def run_validation_gate(deck: dict) -> Tuple[bool, list[str]]:
    """
    Validate a deck JSON object before export begins.

    This function is called at the very start of renderer.render().
    If it returns (False, errors), the export endpoint returns HTTP 422
    with the full error list so the client knows exactly what to fix.

    Checks performed
    ----------------
    1.  schema_version must be "1.0.0"
    2.  aspect_ratio must be "16:9" or "4:3"
    3.  metadata.theme must be a valid enum value
    4.  Deck-level validation_state.blocking_errors must be empty
    5.  slides array must not be empty
    6.  slides must not exceed max_slides_per_deck (100)
    7.  Per-slide: slide_type must be valid
    8.  Per-slide: action_title must be present and <= 60 chars
    9.  Per-slide: slide-level validation_state.blocking_errors must be empty
    10. Per-slide: template.overrides.font_scale must be in [0.8, 1.2]
    11. data_chart: chart_type must be valid
    12. data_chart: series[].values must all be int or float (never strings)
    13. data_chart: len(series.values) must equal len(categories) for non-scatter
    14. data_chart: categories array must not be empty
    15. content_bullets: each bullet must have element_id and text
    16. content_bullets: bullet count must be <= 6
    17. table: headers array must not be empty
    18. table: rows array must not be empty
    19. table: each header must have a 'key' field
    20. visual_split: supporting_text must be present
    21. section_divider: section_title must be present
    22. title_slide: content.headline must be present

    Returns
    -------
    (True, []) if valid.
    (False, [error_strings]) if invalid — each string is a human-readable message.
    """
    errors: list[str] = []

    # ── Deck-level checks ─────────────────────────────────────────────────────

    if deck.get("schema_version") != "1.0.0":
        errors.append(
            f"Unsupported schema_version '{deck.get('schema_version')}'. "
            f"Export service only handles 1.0.0."
        )

    aspect_ratio = deck.get("aspect_ratio", "16:9")
    if aspect_ratio not in VALID_ASPECT_RATIOS:
        errors.append(f"Invalid aspect_ratio '{aspect_ratio}'. Must be '16:9' or '4:3'.")

    theme = deck.get("metadata", {}).get("theme", "")
    if theme not in VALID_THEMES:
        errors.append(
            f"Invalid theme '{theme}'. Must be one of: {sorted(VALID_THEMES)}."
        )

    # Deck-level blocking_errors from Phase 1/2
    deck_blocking = deck.get("validation_state", {}).get("blocking_errors", [])
    for err in deck_blocking:
        errors.append(f"[Deck-level] {err}")

    slides = deck.get("slides", [])
    if not slides:
        errors.append("Deck contains no slides. At least 1 slide is required.")
        return False, errors  # No point continuing per-slide checks

    if len(slides) > 100:
        errors.append(
            f"Deck has {len(slides)} slides. Maximum is 100 per export request."
        )

    # ── Per-slide checks ──────────────────────────────────────────────────────

    for slide in slides:
        sid   = slide.get("slide_id", "unknown")
        sidx  = slide.get("slide_index", "?")
        stype = slide.get("slide_type", "")
        pfx   = f"[Slide {sidx} / {sid[:8]}]"

        # Slide-level blocking errors from Phase 2
        slide_blocking = slide.get("validation_state", {}).get("blocking_errors", [])
        for err in slide_blocking:
            errors.append(f"{pfx} {err}")

        if stype not in VALID_SLIDE_TYPES:
            errors.append(f"{pfx} Invalid slide_type '{stype}'.")
            continue  # Cannot validate content without knowing the type

        # action_title
        action_title = slide.get("action_title", "")
        if not action_title:
            errors.append(f"{pfx} Missing action_title (required on all slide types).")
        elif len(action_title) > 60:
            errors.append(
                f"{pfx} action_title is {len(action_title)} chars (max 60). "
                f"Phase 1 should have truncated this."
            )

        # font_scale bounds
        font_scale = slide.get("template", {}).get("overrides", {}).get("font_scale")
        if font_scale is not None:
            try:
                fs = float(font_scale)
                if not (0.8 <= fs <= 1.2):
                    errors.append(
                        f"{pfx} font_scale {fs} is outside [0.8, 1.2]. "
                        f"Phase 2 should have clamped this."
                    )
            except (TypeError, ValueError):
                errors.append(f"{pfx} font_scale is not a number: {font_scale!r}.")

        content = slide.get("content", {})

        # ── Type-specific content checks ─────────────────────────────────────

        if stype == "title_slide":
            if not content.get("headline"):
                errors.append(
                    f"{pfx} title_slide missing content.headline. "
                    f"Note: action_title is the analyst field; headline is the audience-facing title."
                )

        elif stype == "content_bullets":
            bullets = content.get("bullets", [])
            if not isinstance(bullets, list):
                errors.append(f"{pfx} content.bullets must be an array.")
            else:
                if len(bullets) > 6:
                    errors.append(f"{pfx} content.bullets has {len(bullets)} items (max 6).")
                for bi, bullet in enumerate(bullets):
                    if not bullet.get("element_id"):
                        errors.append(f"{pfx} bullets[{bi}] missing element_id UUID.")
                    if not isinstance(bullet.get("text", ""), str):
                        errors.append(f"{pfx} bullets[{bi}].text must be a string.")

        elif stype == "data_chart":
            chart_type = content.get("chart_type", "")
            if chart_type not in VALID_CHART_TYPES:
                errors.append(f"{pfx} Invalid chart_type '{chart_type}'.")

            chart_data = content.get("chart_data", {})
            categories = chart_data.get("categories", [])
            if not categories:
                errors.append(f"{pfx} chart_data.categories must not be empty.")

            for si, series in enumerate(chart_data.get("series", [])):
                values = series.get("values", [])
                if not values:
                    errors.append(f"{pfx} series[{si}] ('{series.get('name')}') has no values.")
                for vi, val in enumerate(values):
                    if not isinstance(val, (int, float)):
                        errors.append(
                            f"{pfx} series[{si}] ('{series.get('name')}') "
                            f"value[{vi}] is {type(val).__name__}: {val!r}. "
                            f"ALL chart values must be numbers. "
                            f"The AI may have generated quoted strings — "
                            f"fix this in Phase 1 step3_content.py."
                        )
                # Length match (not required for scatter)
                if chart_type != "scatter" and categories and len(values) != len(categories):
                    errors.append(
                        f"{pfx} series[{si}] has {len(values)} values "
                        f"but {len(categories)} categories. They must match."
                    )

        elif stype == "table":
            headers = content.get("headers", [])
            rows    = content.get("rows", [])
            if not headers:
                errors.append(f"{pfx} table missing content.headers.")
            else:
                for hi, hdr in enumerate(headers):
                    if not hdr.get("key"):
                        errors.append(f"{pfx} headers[{hi}] missing 'key' field.")
            if not rows:
                errors.append(f"{pfx} table missing content.rows.")

        elif stype == "visual_split":
            if not content.get("supporting_text"):
                errors.append(f"{pfx} visual_split missing content.supporting_text.")

        elif stype == "section_divider":
            if not content.get("section_title"):
                errors.append(f"{pfx} section_divider missing content.section_title.")

    return len(errors) == 0, errors
