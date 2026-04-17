import json
from tenacity import retry, stop_after_attempt, wait_exponential
from openai import AsyncOpenAI
from core.config import get_settings
from core.prompts import OUTLINE_GENERATION_SYSTEM, OUTLINE_GENERATION_USER
from core.exceptions import PipelineError
from core.logging import get_logger

settings = get_settings()
client = AsyncOpenAI(api_key=settings.openai_api_key)
logger = get_logger(__name__)


def _track_cost(response, model: str, cost_tracker: dict) -> None:
    """Accumulate token costs from an OpenAI response."""
    pricing = {
        "gpt-4o-2024-08-06": {"input": 2.50 / 1_000_000, "output": 10.00 / 1_000_000},
        "gpt-4o-mini":       {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
    }
    p = pricing.get(model, pricing["gpt-4o-mini"])
    in_tok = response.usage.prompt_tokens
    out_tok = response.usage.completion_tokens
    cost_tracker["input_tokens"] += in_tok
    cost_tracker["output_tokens"] += out_tok
    cost_tracker["cost_usd"] += (in_tok * p["input"]) + (out_tok * p["output"])


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
async def generate_outline(prompt: str, intent: dict, cost_tracker: dict) -> list[dict]:
    """
    Step 2: Generate slide outline using gpt-4o.
    Validates the outline structure and ensures first slide is title_slide.
    """
    model = settings.openai_model_primary  # gpt-4o for this step

    try:
        response = await client.chat.completions.create(
            model=model,
            temperature=0.4,
            response_format={"type": "json_object"},
            timeout=settings.openai_timeout_seconds,
            messages=[
                {"role": "system", "content": OUTLINE_GENERATION_SYSTEM},
                {
                    "role": "user",
                    "content": OUTLINE_GENERATION_USER.format(
                        prompt=prompt,
                        intent_json=json.dumps(intent, indent=2),
                        narrative_framework=intent.get("narrative_framework", "pyramid_principle"),
                        industry_vertical=intent.get("industry_vertical", "general"),
                        estimated_slides=intent.get("estimated_slides", 8),
                    )
                }
            ],
            max_tokens=2000,
        )

        # Log if model routing was different
        actual_model = response.model
        if not actual_model.startswith(model.split("-")[0]):
            logger.warning(
                "model_routing_mismatch",
                requested=model,
                actual=actual_model,
                step=2,
            )

        _track_cost(response, model, cost_tracker)

        result = json.loads(response.choices[0].message.content)

        # Handle both array and {"slides": [...]} formats
        if isinstance(result, list):
            outline = result
        elif isinstance(result, dict):
            outline = result.get("slides", result.get("outline", []))
        else:
            raise PipelineError("Step 2 returned unexpected format", step=2)

        # Validate outline structure
        if not outline or not isinstance(outline, list):
            raise PipelineError("Step 2 returned empty or invalid outline", step=2)

        # Ensure first slide is title_slide
        if outline[0].get("slide_type") != "title_slide":
            # Insert title_slide if missing
            title_slide = {
                "slide_type": "title_slide",
                "action_title": f"Presentation: {intent.get('title', 'Untitled')}",
                "narrative_role": "situation",
                "hierarchy_level": 1,
                "layout_hints": {
                    "priority": "balanced",
                    "density": "minimal",
                    "visual_anchor": "center",
                    "suggested_grid_columns": 1
                },
                "speaker_notes_hint": "Welcome and introduce the topic",
                "content_direction": f"Title: {intent.get('title', '')}"
            }
            outline.insert(0, title_slide)
            logger.warning("outline_missing_title_slide", action="inserted_default")

        # Validate each slide has required fields
        required_fields = ["slide_type", "action_title", "narrative_role"]
        for i, slide in enumerate(outline):
            missing = [f for f in required_fields if f not in slide]
            if missing:
                logger.warning(
                    "outline_slide_missing_fields",
                    slide_index=i,
                    missing=missing
                )
                # Set defaults for missing fields
                for f in missing:
                    if f == "slide_type":
                        slide[f] = "content_bullets"
                    elif f == "action_title":
                        slide[f] = f"Slide {i+1}"
                    elif f == "narrative_role":
                        slide[f] = "content"

        return outline

    except json.JSONDecodeError as e:
        raise PipelineError(f"Step 2 returned invalid JSON: {e}", step=2, retryable=True)
