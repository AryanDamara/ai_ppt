import json
from tenacity import retry, stop_after_attempt, wait_exponential
from openai import AsyncOpenAI
from core.config import get_settings
from core.prompts import VALIDATION_SYSTEM, VALIDATION_USER
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
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    reraise=True,
)
async def validate_and_flag_slide(slide: dict, cost_tracker: dict) -> dict:
    """
    Step 4: Validate slide content and set hallucination risk flags.
    Uses gpt-4o-mini for fast validation.
    Non-blocking: validation failures don't stop the pipeline.
    """
    model = settings.openai_model_fast  # gpt-4o-mini is sufficient for validation

    # Extract slide type from content structure
    slide_type = _infer_slide_type(slide)
    industry = "general"

    try:
        response = await client.chat.completions.create(
            model=model,
            temperature=0.1,  # Low temperature for consistent validation
            response_format={"type": "json_object"},
            timeout=settings.openai_timeout_seconds,
            messages=[
                {"role": "system", "content": VALIDATION_SYSTEM},
                {
                    "role": "user",
                    "content": VALIDATION_USER.format(
                        slide_json=json.dumps(slide, indent=2),
                        slide_type=slide_type,
                        industry_vertical=industry,
                    )
                }
            ],
            max_tokens=500,
        )

        _track_cost(response, model, cost_tracker)

        result = json.loads(response.choices[0].message.content)

        # Merge validation results back into slide
        validated_slide = {
            **slide,
            "action_title": result.get("action_title", slide.get("action_title", "")),
        }

        # Set hallucination risk flags
        hallucination_flags = result.get("hallucination_risk_flags", [])

        # PHASE 1: Auto-flag numerical data as unverified (no RAG yet)
        if slide_type == "data_chart":
            if "numerical_unverified" not in hallucination_flags:
                hallucination_flags.append("numerical_unverified")

        # Add validation notes if present
        validation_notes = result.get("validation_notes", "")
        if validation_notes:
            logger.info("slide_validation_notes", notes=validation_notes[:200])

        return {
            "action_title": validated_slide["action_title"],
            "content": slide.get("content", {}),
            "hallucination_risk_flags": hallucination_flags,
        }

    except Exception as e:
        # Validation failure is non-blocking — return original slide with default flags
        logger.warning("slide_validation_failed", error=str(e), slide_type=slide_type)
        return {
            "action_title": slide.get("action_title", ""),
            "content": slide.get("content", {}),
            "hallucination_risk_flags": ["numerical_unverified"],
        }


def _infer_slide_type(slide: dict) -> str:
    """Infer slide type from content structure."""
    content = slide.get("content", {})

    if "chart_type" in content:
        return "data_chart"
    elif "bullets" in content:
        return "content_bullets"
    elif "supporting_text" in content:
        return "visual_split"
    elif "headers" in content and "rows" in content:
        return "table"
    elif "section_title" in content:
        return "section_divider"
    elif "headline" in content:
        return "title_slide"

    return "unknown"
