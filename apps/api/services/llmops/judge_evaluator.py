"""
LLM-as-Judge evaluation — automated quality scoring for generated content.

THREE JUDGES:
  1. Faithfulness Judge: Does the slide content match the user's prompt intent?
  2. Schema Compliance Judge: Does the JSON match the expected schema?
  3. Hallucination Judge: Does the content contain fabricated facts?

COST:
  Each judge call: ~500 tokens = ~$0.0025
  50 test cases × 3 judges = 150 calls = ~$0.38 per eval run
"""
from __future__ import annotations
import json
import logging
from dataclasses import dataclass, field
from typing import Optional

import openai

logger = logging.getLogger(__name__)

# Judge score thresholds
FAITHFULNESS_MIN      = 0.75
SCHEMA_COMPLIANCE_MIN = 0.90
HALLUCINATION_MAX     = 0.20


@dataclass
class JudgeResult:
    """Result from one LLM-as-Judge evaluation."""
    judge_name:   str
    score:        float
    reasoning:    str
    issues:       list[str] = field(default_factory=list)
    raw_response: str = ""

    @property
    def passed(self) -> bool:
        if self.judge_name == "hallucination":
            return self.score <= HALLUCINATION_MAX
        elif self.judge_name == "schema_compliance":
            return self.score >= SCHEMA_COMPLIANCE_MIN
        else:
            return self.score >= FAITHFULNESS_MIN


@dataclass
class EvalResult:
    """Complete evaluation result for one test case."""
    test_case_id:      str
    prompt_name:       str
    prompt_version:    str
    input_data:        dict
    generated_output:  str
    faithfulness:      Optional[JudgeResult] = None
    schema_compliance: Optional[JudgeResult] = None
    hallucination:     Optional[JudgeResult] = None
    error:             Optional[str] = None

    @property
    def overall_passed(self) -> bool:
        judges = [self.faithfulness, self.schema_compliance, self.hallucination]
        active = [j for j in judges if j is not None]
        return all(j.passed for j in active) if active else False

    @property
    def summary_scores(self) -> dict:
        return {
            "faithfulness":      self.faithfulness.score if self.faithfulness else None,
            "schema_compliance": self.schema_compliance.score if self.schema_compliance else None,
            "hallucination":     self.hallucination.score if self.hallucination else None,
            "overall_passed":    self.overall_passed,
        }


class JudgeEvaluator:
    """Runs LLM-as-Judge evaluations against generated content."""

    def __init__(self):
        self._client = openai.AsyncOpenAI()

    async def evaluate(
        self,
        test_case_id:       str,
        prompt_name:        str,
        input_data:         dict,
        generated_output:   str,
        run_faithfulness:   bool = True,
        run_schema:         bool = True,
        run_hallucination:  bool = True,
    ) -> EvalResult:
        """Run all applicable judges on a generated output."""
        from services.llmops.prompt_registry import get_registry
        registry = get_registry()
        prompt   = registry.get(prompt_name)

        result = EvalResult(
            test_case_id=test_case_id,
            prompt_name=prompt_name,
            prompt_version=prompt.version,
            input_data=input_data,
            generated_output=generated_output,
        )

        import asyncio
        tasks = []
        if run_faithfulness:
            tasks.append(("faithfulness", self._judge_faithfulness(input_data, generated_output)))
        if run_schema:
            tasks.append(("schema_compliance", self._judge_schema(generated_output)))
        if run_hallucination:
            tasks.append(("hallucination", self._judge_hallucination(input_data, generated_output)))

        judge_results = await asyncio.gather(
            *[task for _, task in tasks],
            return_exceptions=True,
        )

        for (name, _), judge_result in zip(tasks, judge_results):
            if isinstance(judge_result, Exception):
                logger.error(f"Judge '{name}' failed: {judge_result}")
                judge_result = JudgeResult(
                    judge_name=name, score=0.5,
                    reasoning=f"Judge failed: {judge_result}",
                )
            setattr(result, name, judge_result)

        return result

    async def _judge_faithfulness(self, input_data: dict, generated_output: str) -> JudgeResult:
        """Judge: Does the generated content faithfully represent the user's intent?"""
        user_prompt_text = input_data.get("user_prompt", input_data.get("prompt", ""))
        industry         = input_data.get("industry", "general")

        evaluation_prompt = f"""
You are evaluating whether an AI-generated presentation outline faithfully addresses the user's request.

USER REQUEST: "{user_prompt_text}"
INDUSTRY: {industry}

GENERATED OUTPUT:
{generated_output[:3000]}

Evaluate FAITHFULNESS on a scale of 0.0 to 1.0:
- 1.0: Content directly and completely addresses the user's request
- 0.75: Content mostly addresses the request with minor gaps
- 0.50: Content partially addresses the request
- 0.25: Content has some relation but misses the main intent
- 0.0: Content is completely unrelated to the request

Respond with ONLY valid JSON:
{{"score": float, "reasoning": "one sentence explanation", "issues": ["issue 1", "issue 2"]}}
"""
        return await self._call_judge("faithfulness", evaluation_prompt, "powerful")

    async def _judge_schema(self, generated_output: str) -> JudgeResult:
        """Judge: Does the generated output comply with the expected JSON schema?"""
        evaluation_prompt = f"""
You are evaluating whether an AI-generated JSON output complies with the presentation schema.

GENERATED OUTPUT:
{generated_output[:3000]}

SCHEMA REQUIREMENTS:
- Must be valid JSON
- Must have: "title" (string), "narrative_framework" (enum), "slides" (array)
- Each slide must have: "slide_index" (int), "slide_type" (enum), "action_title" (string ≤60 chars)
- action_title must be ≤ 60 characters
- slide_type must be one of: title_slide, content_bullets, data_chart, visual_split, table, section_divider

Respond with ONLY valid JSON:
{{"score": float, "reasoning": "one sentence", "issues": ["specific schema violation 1", "violation 2"]}}
"""
        return await self._call_judge("schema_compliance", evaluation_prompt, "fast")

    async def _judge_hallucination(self, input_data: dict, generated_output: str) -> JudgeResult:
        """Judge: Does the output contain hallucinated facts? Score inverted: lower = better."""
        evaluation_prompt = f"""
You are evaluating whether an AI-generated presentation contains hallucinated facts.

USER INPUT: "{input_data.get('user_prompt', '')}"

GENERATED OUTPUT:
{generated_output[:3000]}

Check for hallucinations:
1. Specific statistics or numbers not stated in the input
2. Company names, product names, or people invented by the AI
3. Historical events or dates that cannot be verified from the input

Score 0.0-1.0 where:
  0.0 = No hallucinations
  0.5 = Some unverifiable claims but not clearly false
  1.0 = Clear fabrications present

Respond with ONLY valid JSON:
{{"score": float, "reasoning": "one sentence", "issues": ["specific hallucination 1"]}}
"""
        return await self._call_judge("hallucination", evaluation_prompt, "powerful")

    async def _call_judge(self, judge_name: str, prompt: str, model_class: str) -> JudgeResult:
        """Make the judge API call and parse the response."""
        from services.llmops.model_router import get_model_for_class
        model = get_model_for_class(model_class)

        try:
            response = await self._client.chat.completions.create(
                model=model,
                max_tokens=300,
                temperature=0.0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "You are an AI evaluation judge. Always respond with valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
            )

            raw = response.choices[0].message.content or "{}"
            data = json.loads(raw)

            return JudgeResult(
                judge_name=judge_name,
                score=float(data.get("score", 0.5)),
                reasoning=data.get("reasoning", ""),
                issues=data.get("issues", []),
                raw_response=raw,
            )

        except json.JSONDecodeError as e:
            logger.error(f"Judge {judge_name} returned invalid JSON: {e}")
            return JudgeResult(
                judge_name=judge_name,
                score=0.5,
                reasoning=f"Judge returned invalid JSON: {e}",
            )
        except Exception as e:
            logger.error(f"Judge {judge_name} API call failed: {e}")
            raise
