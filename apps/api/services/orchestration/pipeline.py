import asyncio
import json
from uuid import uuid4
from datetime import datetime, timezone
from typing import Callable

from core.config import get_settings
from core.logging import get_logger
from .step1_intent import classify_intent
from .step2_outline import generate_outline
from .step3_content import generate_slide_content
from .step4_validate import validate_and_flag_slide

settings = get_settings()
logger = get_logger(__name__)

# Accumulated cost tracking across all LLM calls in one pipeline run
MODEL_PRICING = {
    "gpt-4o-2024-08-06": {"input": 2.50 / 1_000_000, "output": 10.00 / 1_000_000},
    "gpt-4o-mini":       {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
}


async def run_pipeline(
    job_id: str,
    request: dict,
    publish_event: Callable,
    tenant_id: str | None = None,
    doc_ids: list[str] | None = None,
) -> dict:
    """
    4-step AI orchestration pipeline.
    Tracks token costs. Publishes events per slide. Never lets one bad slide
    kill the rest.
    """
    presentation_id = str(uuid4())
    prompt = request["prompt"]
    theme = request.get("theme", "modern_light")
    cost_tracker = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}

    # ── STEP 1: Intent (gpt-4o-mini) ─────────────────────────────────────────
    publish_event(job_id, {
        "type": "pipeline_step", "step": 1, "job_id": job_id,
        "name": "Classifying presentation type and structure",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    intent = await classify_intent(prompt, request, cost_tracker)

    # ── STEP 2: Outline (gpt-4o) ──────────────────────────────────────────────
    publish_event(job_id, {
        "type": "pipeline_step", "step": 2, "job_id": job_id,
        "name": "Building slide structure and narrative flow",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    outline = await generate_outline(prompt, intent, cost_tracker)
    total_slides = len(outline)

    # ── STEP 3 + 4: Per-slide (parallel, each with timeout) ───────────────────
    async def generate_one_slide(slide_outline: dict, index: int) -> dict | None:
        try:
            # Primary + 3 alternatives — all in parallel
            tasks = [
                generate_slide_content(
                    slide_outline=slide_outline,
                    deck_context={
                        "prompt": prompt,
                        "theme": theme,
                        "narrative_framework": intent["narrative_framework"],
                        "industry_vertical": intent["industry_vertical"],
                        "slide_index": index,
                        "total_slides": total_slides,
                    },
                    temperature=temp,
                    cost_tracker=cost_tracker,
                    tenant_id=tenant_id,
                    doc_ids=doc_ids,
                )
                for temp in [0.3, 0.5, 0.7, 0.9]
            ]

            # Per-slide timeout — 15 seconds before giving up on this slide
            results = await asyncio.gather(
                *[
                    asyncio.wait_for(t, timeout=settings.slide_generation_timeout_seconds)
                    for t in tasks
                ],
                return_exceptions=True,
            )

            primary = results[0]
            if isinstance(primary, Exception):
                raise primary

            alternatives = []
            for i, alt in enumerate(results[1:], 1):
                if not isinstance(alt, Exception):
                    alternatives.append({
                        "variant_id": str(uuid4()),
                        "action_title": alt.get("action_title", ""),
                        "confidence_score": round(0.9 - (i * 0.1), 2),
                    })

            # Step 4: validate + flag (gpt-4o-mini)
            validated = await validate_and_flag_slide(primary, cost_tracker)

            # Increment Redis counter for partial_failure detection
            from workers.celery_app import redis
            redis.hincrby(f"job:{job_id}", "slides_completed", 1)

            slide = {
                "slide_id": str(uuid4()),
                "slide_type": slide_outline["slide_type"],
                "slide_index": index,
                "action_title": validated["action_title"],
                "content": validated["content"],
                "speaker_notes": slide_outline.get("speaker_notes_hint", ""),
                "outline_context": {
                    "hierarchy_level": slide_outline.get("hierarchy_level", 2),
                    "narrative_role": slide_outline["narrative_role"],
                    "estimated_duration_seconds": 60,
                },
                "layout_hints": slide_outline.get("layout_hints", {
                    "priority": "balanced",
                    "density": "standard",
                    "visual_anchor": "none",
                    "suggested_grid_columns": 1,
                }),
                "ai_metadata": {
                    "generation_confidence": 0.85,
                    "alternative_generations": alternatives,
                    "hallucination_risk_flags": validated.get("hallucination_risk_flags", []),
                    "human_review_status": "pending",
                },
                "validation_state": {
                    "schema_compliant": True,
                    "blocking_errors": [],
                    "layout_warnings": [],
                },
            }

            publish_event(job_id, {
                "type": "slide_ready",
                "job_id": job_id,
                "slide": slide,
                "slide_index": index,
                "total_slides": total_slides,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            return slide

        except asyncio.TimeoutError:
            publish_event(job_id, {
                "type": "slide_failed", "job_id": job_id,
                "slide_index": index,
                "slide_type": slide_outline.get("slide_type", "unknown"),
                "error": f"Slide timed out after {settings.slide_generation_timeout_seconds}s",
                "retry_id": str(uuid4()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return None

        except Exception as exc:
            logger.error("slide_generation_failed", slide_index=index, error=str(exc))
            publish_event(job_id, {
                "type": "slide_failed", "job_id": job_id,
                "slide_index": index,
                "slide_type": slide_outline.get("slide_type", "unknown"),
                "error": str(exc)[:200],
                "retry_id": str(uuid4()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return None

    slide_results = await asyncio.gather(
        *[generate_one_slide(outline[i], i) for i in range(total_slides)],
        return_exceptions=False,
    )

    slides = sorted(
        [s for s in slide_results if s is not None],
        key=lambda s: s["slide_index"],
    )

    deck = {
        "schema_version": "1.0.0",
        "presentation_id": presentation_id,
        "metadata": {
            "title": intent.get("title", prompt[:80]),
            "subtitle": intent.get("subtitle", ""),
            "audience": intent.get("audience", request.get("audience", "")),
            "theme": theme,
            "industry_vertical": intent["industry_vertical"],
            "language": intent.get("language", "en-US"),
        },
        "generation_metadata": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "model_version": settings.openai_model_primary,
            "generation_status": "complete" if len(slides) == total_slides else "partial_failure",
            "pipeline_version": settings.pipeline_version,
            "job_id": job_id,
        },
        "outline_context": {
            "narrative_framework": intent["narrative_framework"],
            "total_slides_projected": total_slides,
        },
        "validation_state": {
            "schema_compliant": True,
            "blocking_errors": [],
            "layout_warnings": [],
        },
        "slides": slides,
        # Internal cost tracking — stripped before sending to client
        "_cost_metadata": {
            "total_input_tokens": cost_tracker["input_tokens"],
            "total_output_tokens": cost_tracker["output_tokens"],
            "estimated_cost_usd": round(cost_tracker["cost_usd"], 6),
        },
    }

    return deck
