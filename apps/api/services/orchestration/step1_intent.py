import json
from tenacity import retry, stop_after_attempt, wait_exponential
from openai import AsyncOpenAI
from core.config import get_settings
from core.prompts import INTENT_CLASSIFICATION_SYSTEM, INTENT_CLASSIFICATION_USER
from core.exceptions import PipelineError, ModelMismatchError
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
async def classify_intent(prompt: str, request: dict, cost_tracker: dict) -> dict:
    """
    Step 1: Classify intent using gpt-4o-mini.
    Falls back to gpt-4o-mini if primary model is unavailable.
    Validates enum fields and clamps estimated_slides.
    """
    model = settings.openai_model_fast  # gpt-4o-mini for this step

    try:
        response = await client.chat.completions.create(
            model=model,
            temperature=0.3,
            response_format={"type": "json_object"},
            timeout=settings.openai_timeout_seconds,
            messages=[
                {"role": "system", "content": INTENT_CLASSIFICATION_SYSTEM},
                {
                    "role": "user",
                    "content": INTENT_CLASSIFICATION_USER.format(
                        prompt=prompt,
                        theme=request.get("theme", "modern_light"),
                        narrative_framework_pref=request.get("narrative_framework", "auto"),
                        industry_vertical_pref=request.get("industry_vertical", "general"),
                        audience_pref=request.get("audience", "general business audience"),
                        language_pref=request.get("language", "en-US"),
                    )
                }
            ],
            max_tokens=500,
        )

        # Log if model routing was different from what was requested
        actual_model = response.model
        if not actual_model.startswith(model.split("-")[0]):
            logger.warning(
                "model_routing_mismatch",
                requested=model,
                actual=actual_model,
                step=1,
            )

        _track_cost(response, model, cost_tracker)

        result = json.loads(response.choices[0].message.content)

        # Validate and sanitize enum fields
        valid_frameworks = [
            "pyramid_principle", "hero_journey", "chronological",
            "problem_solution", "compare_contrast"
        ]
        valid_verticals = [
            "general", "healthcare", "financial_services",
            "government", "technology", "legal"
        ]

        if result.get("narrative_framework") not in valid_frameworks:
            result["narrative_framework"] = "pyramid_principle"

        if result.get("industry_vertical") not in valid_verticals:
            result["industry_vertical"] = "general"

        result["estimated_slides"] = max(3, min(20, int(result.get("estimated_slides", 8))))

        required = ["narrative_framework", "industry_vertical", "estimated_slides"]
        missing = [f for f in required if f not in result]
        if missing:
            raise PipelineError(f"Step 1 missing required fields: {missing}", step=1)

        return result

    except json.JSONDecodeError as e:
        raise PipelineError(f"Step 1 returned invalid JSON: {e}", step=1, retryable=True)
