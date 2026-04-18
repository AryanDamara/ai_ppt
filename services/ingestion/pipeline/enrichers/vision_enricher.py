"""
Vision enricher — GPT-4o Vision descriptions for charts and diagrams.

WHY THIS IS CRITICAL:
  40-60% of business document information lives in charts, graphs, and diagrams.
  Without vision enrichment, a RAG system is blind to:
    - Revenue trend charts (exact growth rates visible only in the chart)
    - Org charts (reporting structures)
    - Architecture diagrams (system relationships)
    - Process flow diagrams
    - Comparison matrices

  GPT-4o Vision reads the image and produces a dense analytical description
  containing all the specific data points, trends, and insights visible in the image.
  This description is embedded as a regular text chunk — the chart becomes searchable.

Cost control:
  - Concurrency semaphore (default 5 concurrent calls)
  - Image deduplication: SHA256 hash → cache (skips identical images)
  - Classification step: decorative images (logos, photos) are skipped entirely
  - Max retries: 3 with exponential backoff

Output quality:
  - "analytical" mode for charts/graphs: all data points, units, trends, insight
  - "contextual" mode for diagrams: structure, relationships, key components
  - "skip" for decorative: return None
"""
from __future__ import annotations
import asyncio
import base64
import hashlib
import logging
from typing import Optional

from tenacity import (
    retry, stop_after_attempt, wait_exponential,
    retry_if_exception_type,
)

from core.config import get_settings

settings = get_settings()
logger   = logging.getLogger(__name__)

# Global semaphore — shared across all concurrent ingestion tasks
_vision_semaphore = asyncio.Semaphore(settings.vision_concurrent_calls)

# In-memory dedup cache: image_hash → description (or None for skipped)
_VISION_CACHE: dict[str, Optional[str]] = {}

# ── Prompts ────────────────────────────────────────────────────────────────────

_CLASSIFY_PROMPT = """
Classify this image into exactly ONE category. Respond with ONLY the category name.

Categories:
- chart_or_graph: Bar chart, line graph, pie chart, scatter plot, histogram, waterfall chart
- table_image: A table rendered as an image (rows and columns with data)
- diagram: Flowchart, process diagram, org chart, architecture diagram, network diagram
- decorative: Logo, photograph, stock image, icon, decorative element with no data

Respond with exactly one of: chart_or_graph, table_image, diagram, decorative
"""

_ANALYTICAL_PROMPT = """
You are analyzing a chart or graph from a business document.
Produce a detailed, factual analytical description optimized for AI retrieval.

Include ALL of the following that are present:
1. Chart type (bar chart, line graph, pie chart, waterfall chart, etc.)
2. Chart title or main heading text (exact words if visible)
3. X-axis: label and all category names or time periods
4. Y-axis: label and units
5. Every data series name
6. Specific data values for each data point (exact numbers, not approximations)
7. Percentage values, growth rates, differences between periods
8. Trends: ascending, descending, peak periods, trough periods
9. Any annotations, callouts, or highlighted data points in the chart
10. The single key business insight this chart shows

Write as dense, factual prose. Do NOT use markdown. Include every number visible.
Precision is critical — the exact figures will be used for fact-checking.
"""

_TABLE_IMAGE_PROMPT = """
You are analyzing a table rendered as an image from a business document.
Extract all data accurately.

Provide:
1. Table title (if visible)
2. Column headers (exact text)
3. All rows with their values (row header: value for each column)
4. Any totals, subtotals, or summary rows
5. Units or currency (if shown in headers or footnotes)
6. Any highlighted, bold, or color-coded cells (and why they are highlighted)

Format as dense prose: [Row name]: [col1_header] = [value], [col2_header] = [value]. etc.
"""

_DIAGRAM_PROMPT = """
You are analyzing a diagram from a business document.
Provide a structured description for AI retrieval.

Include:
1. Diagram type (flowchart, org chart, architecture diagram, etc.)
2. Title (if visible)
3. Main components or nodes (label each one)
4. Connections and relationships between components
5. Direction of flow (if applicable)
6. Any labels on connections/arrows
7. Key insight or purpose this diagram communicates

Write as factual prose. Be specific about names and relationships shown.
"""


class VisionEnricher:
    """Produces text descriptions of charts/diagrams using GPT-4o Vision."""

    def __init__(self):
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def describe_image(
        self,
        image_bytes: bytes,
        caption:     Optional[str] = None,
        page_number: int = 0,
    ) -> Optional[str]:
        """
        Generate a searchable text description of an image.

        Returns None if:
        - Image is decorative (logo, photo, icon)
        - Image is too small (< 1000 bytes) — likely an artifact
        - All retries exhausted (returns a placeholder instead of None)

        Parameters
        ----------
        image_bytes : PNG or JPEG image bytes from ParsedElement.image_bytes
        caption     : figure caption from the document (adds context to prompt)
        page_number : for logging only
        """
        if not image_bytes or len(image_bytes) < 1000:
            return None

        # Deduplication check
        img_hash = hashlib.sha256(image_bytes).hexdigest()[:20]
        if img_hash in _VISION_CACHE:
            logger.debug(f"Vision cache hit: {img_hash}")
            return _VISION_CACHE[img_hash]

        async with _vision_semaphore:
            try:
                # Step 1: Classify
                classification = await self._classify(image_bytes)

                if classification == "decorative":
                    _VISION_CACHE[img_hash] = None
                    return None

                # Step 2: Describe based on classification
                prompt = {
                    "chart_or_graph": _ANALYTICAL_PROMPT,
                    "table_image":    _TABLE_IMAGE_PROMPT,
                    "diagram":        _DIAGRAM_PROMPT,
                }.get(classification, _ANALYTICAL_PROMPT)

                # Append caption context
                if caption:
                    prompt += f"\n\nFigure caption from document: \"{caption}\""
                if page_number:
                    prompt += f"\n\nThis visual appears on page {page_number}."

                description = await self._vision_call(image_bytes, prompt, max_tokens=700)
                if description:
                    description = f"[{classification.replace('_', ' ').title()}] " + description

                _VISION_CACHE[img_hash] = description
                return description

            except Exception as e:
                logger.error(f"Vision enrichment error (page {page_number}): {e}")
                fallback = f"[Image on page {page_number}: vision description unavailable due to processing error]"
                _VISION_CACHE[img_hash] = fallback
                return fallback

    async def _classify(self, image_bytes: bytes) -> str:
        """Quick classification call to avoid full description of decorative images."""
        try:
            result = await self._vision_call(image_bytes, _CLASSIFY_PROMPT, max_tokens=10)
            result = (result or "").strip().lower().replace("_", "_")
            for cat in ("chart_or_graph", "table_image", "diagram", "decorative"):
                if cat in result:
                    return cat
            return "chart_or_graph"   # Safe default: describe unknown images
        except Exception:
            return "chart_or_graph"

    @retry(
        stop=stop_after_attempt(settings.vision_max_retries),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(Exception),
        reraise=False,
    )
    async def _vision_call(
        self,
        image_bytes: bytes,
        prompt: str,
        max_tokens: int = 700,
    ) -> Optional[str]:
        """Make a GPT-4o Vision API call with retry."""
        import openai

        encoded    = base64.b64encode(image_bytes).decode("utf-8")
        media_type = "image/png" if image_bytes[:4] == b'\x89PNG' else "image/jpeg"

        response = await self._client.chat.completions.create(
            model=settings.openai_vision_model,
            max_tokens=max_tokens,
            timeout=45,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url":    f"data:{media_type};base64,{encoded}",
                            "detail": "high",
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
        )

        content = response.choices[0].message.content
        return content.strip() if content else None
