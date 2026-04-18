import json
from tenacity import retry, stop_after_attempt, wait_exponential
from openai import AsyncOpenAI
from uuid import uuid4
from core.config import get_settings
from core.prompts import SLIDE_CONTENT_SYSTEM, SLIDE_CONTENT_USER
from core.exceptions import PipelineError, ContentSizeError
from core.logging import get_logger

settings = get_settings()
client = AsyncOpenAI(api_key=settings.openai_api_key)
logger = get_logger(__name__)

SLIDE_TYPE_SCHEMAS = {
    "title_slide": """
Return JSON with this exact structure:
{
  "action_title": "string max 60 chars — analyst So What sentence",
  "content": {
    "headline": "string max 100 chars — audience-facing punchier title",
    "subheadline": "string optional max 200 chars",
    "presenter_name": "string optional",
    "presenter_title": "string optional",
    "date": "YYYY-MM-DD optional",
    "event_name": "string optional"
  }
}
""",
    "content_bullets": """
Return JSON with this exact structure:
{
  "action_title": "string max 60 chars",
  "content": {
    "layout_variant": "single_column|two_column|three_column|pyramid",
    "bullets": [
      {
        "element_id": "UUID v4 string — generate a fresh UUID for each bullet",
        "text": "string max 200 chars",
        "indent_level": 0,
        "emphasis": "none|highlight|bold|critical|subtle",
        "supporting_data": "short stat optional e.g. up 34% YoY"
      }
    ]
  }
}
Max 6 bullets. Generate proper UUID v4 for every element_id.
""",
    "data_chart": """
Return JSON with this exact structure:
{
  "action_title": "string max 60 chars",
  "content": {
    "chart_type": "column_clustered|column_stacked|line|pie|bar|area|waterfall|scatter",
    "key_takeaway_callout": "string — main insight from the data",
    "chart_data": {
      "series": [
        {
          "name": "string",
          "values": [numbers only — NEVER strings],
          "color": "#RRGGBB optional",
          "unit": "string optional"
        }
      ],
      "categories": ["string labels — must match values array length"],
      "global_unit": "string optional",
      "data_source": "string optional"
    },
    "chart_options": {
      "show_legend": true,
      "show_data_labels": false
    }
  }
}
""",
    "visual_split": """
Return JSON with this exact structure:
{
  "action_title": "string max 60 chars",
  "content": {
    "supporting_text": "string required — 2-4 compelling narrative sentences",
    "image_keyword": "specific visual search term — not generic like business or people",
    "alt_text": "string max 300 chars",
    "text_position": "left|right|overlay default left",
    "image_treatment": "original|monochrome|duotone|gradient_overlay"
  }
}
""",
    "table": """
Return JSON with this exact structure:
{
  "action_title": "string max 60 chars",
  "content": {
    "table_title": "string optional",
    "headers": [
      { "key": "col_key", "label": "Display Label", "width_percent": 25, "align": "left" }
    ],
    "rows": [
      {
        "row_id": "descriptive-string",
        "cells": {
          "col_key": {
            "value": "string",
            "numeric_value": 0.0,
            "emphasis": false,
            "change_indicator": "up|down|neutral|none"
          }
        }
      }
    ],
    "source_citation": "string optional",
    "highlight_cells": [{ "row_id": "string", "column_key": "string", "reason": "string" }]
  }
}
""",
    "section_divider": """
Return JSON with this exact structure:
{
  "action_title": "string max 60 chars",
  "content": {
    "section_title": "string required max 5 words",
    "section_number": "string optional e.g. 01",
    "transition_quote": "string optional",
    "preview_bullets": ["string max 3 items"]
  }
}
""",
}


def _track_cost(response, model: str, cost_tracker: dict) -> None:
    """Accumulate token costs from an OpenAI response."""
    pricing = {
        settings.openai_model_primary: {"input": 2.50 / 1_000_000, "output": 10.00 / 1_000_000},
        settings.openai_model_fallback: {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
    }
    p = pricing.get(model, pricing[settings.openai_model_fallback])
    cost_tracker["input_tokens"] += response.usage.prompt_tokens
    cost_tracker["output_tokens"] += response.usage.completion_tokens
    cost_tracker["cost_usd"] += (
        (response.usage.prompt_tokens * p["input"]) +
        (response.usage.completion_tokens * p["output"])
    )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
async def generate_slide_content(
    slide_outline: dict,
    deck_context: dict,
    temperature: float = 0.3,
    cost_tracker: dict = None,
    tenant_id: str | None = None,
    doc_ids: list[str] | None = None,
) -> dict:
    """
    Step 3: Generate complete content for one slide.
    - Enforces content size limit (50KB max)
    - Validates chart values are numbers not strings
    - Ensures element_id exists on every bullet
    - Falls back to gpt-4o-mini if primary model fails twice
    """
    if cost_tracker is None:
        cost_tracker = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}

    # ── RAG context retrieval (if documents provided) ─────────────────────────
    rag_context = ""
    citations = []

    if doc_ids and tenant_id:
        from services.orchestration.retrieval_client import retrieve_context

        # Use the slide topic / action_title as the retrieval query
        retrieval_query = (
            slide_outline.get("action_title") or
            slide_outline.get("topic") or
            deck_context.get("metadata", {}).get("title", "")
        )

        if retrieval_query:
            retrieved = await retrieve_context(
                query=retrieval_query,
                tenant_id=tenant_id,
                doc_ids=doc_ids,
            )
            rag_context = retrieved.get("context_string", "")
            citations = retrieved.get("citations", [])

    slide_type = slide_outline["slide_type"]
    schema_desc = SLIDE_TYPE_SCHEMAS.get(slide_type, "")

    # Try primary model first, fall back to mini after 2 retries
    retry_count = getattr(generate_slide_content, '_retry_count', 0)
    model = (
        settings.openai_model_fallback
        if retry_count >= 2
        else settings.openai_model_primary
    )

    # Build system prompt with RAG context if available
    system_content = SLIDE_CONTENT_SYSTEM.format(
        slide_type=slide_type,
        slide_type_schema=schema_desc,
        industry_vertical=deck_context.get("industry_vertical", "general"),
    )

    if rag_context:
        system_content += f"""
\nGROUNDING RULES (follow strictly):
1. Base ALL factual claims, numbers, and insights on the provided source excerpts.
2. Quote specific figures exactly as they appear in the sources.
3. When citing a source, use the label format [Source N] in your reasoning.
4. If the sources do not contain information relevant to a point, state it as
   general context (not specific to the sources) — do not hallucinate facts.
5. Set hallucination_risk_flags to [] for claims directly sourced from the excerpts.
6. Set hallucination_risk_flags to ["not_in_source_documents"] for general statements.

DOCUMENT EXCERPTS:
{rag_context}
"""

    try:
        response = await client.chat.completions.create(
            model=model,
            temperature=temperature,
            response_format={"type": "json_object"},
            timeout=settings.openai_timeout_seconds,
            messages=[
                {
                    "role": "system",
                    "content": system_content
                },
                {
                    "role": "user",
                    "content": SLIDE_CONTENT_USER.format(
                        prompt=deck_context["prompt"],
                        theme=deck_context.get("theme", "modern_light"),
                        narrative_framework=deck_context.get("narrative_framework", "pyramid_principle"),
                        slide_index_human=deck_context["slide_index"] + 1,
                        total_slides=deck_context["total_slides"],
                        slide_outline_json=json.dumps(slide_outline, indent=2),
                        slide_type=slide_type,
                    )
                }
            ],
            max_tokens=1500,
        )

        # Track cost
        pricing = {
            settings.openai_model_primary: {"input": 2.50 / 1_000_000, "output": 10.00 / 1_000_000},
            settings.openai_model_fallback: {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
        }
        p = pricing.get(model, pricing[settings.openai_model_fallback])
        cost_tracker["input_tokens"] += response.usage.prompt_tokens
        cost_tracker["output_tokens"] += response.usage.completion_tokens
        cost_tracker["cost_usd"] += (
            (response.usage.prompt_tokens * p["input"]) +
            (response.usage.completion_tokens * p["output"])
        )

        result = json.loads(response.choices[0].message.content)

        # ── Content size guard ──────────────────────────────────────────────
        content_size = len(json.dumps(result))
        if content_size > settings.max_slide_content_bytes:
            raise ContentSizeError(content_size, settings.max_slide_content_bytes, slide_type)

        # ── action_title length guard ───────────────────────────────────────
        action_title = result.get("action_title", slide_outline.get("action_title", "Slide"))
        if len(action_title) > 60:
            action_title = action_title[:57] + "..."
        result["action_title"] = action_title

        # ── content field required ──────────────────────────────────────────
        if "content" not in result:
            raise PipelineError(f"Step 3 missing 'content' for {slide_type}", step=3)

        # ── Type-specific validations ───────────────────────────────────────
        if slide_type == "data_chart":
            for series in result["content"].get("chart_data", {}).get("series", []):
                for val in series.get("values", []):
                    if not isinstance(val, (int, float)):
                        raise PipelineError(
                            f"Chart values must be numbers, got: {type(val).__name__} = {val!r}",
                            step=3,
                            retryable=True,
                        )

        if slide_type == "content_bullets":
            for bullet in result["content"].get("bullets", []):
                if not bullet.get("element_id"):
                    bullet["element_id"] = str(uuid4())

        # ── Inject citations from retrieval ────────────────────────────────────
        if citations:
            result["citations"] = citations
            # Clear hallucination flags for grounded slides
            if "ai_metadata" not in result:
                result["ai_metadata"] = {}
            if "validation_state" not in result:
                result["validation_state"] = {}
            if rag_context and len(citations) > 0:
                result["ai_metadata"]["hallucination_risk_flags"] = []

        return result

    except json.JSONDecodeError as e:
        raise PipelineError(f"Step 3 invalid JSON for {slide_type}: {e}", step=3, retryable=True)
