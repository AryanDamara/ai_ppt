"""
Evaluation runner — batch runs judges against a prompt version.

USAGE:
  python -m services.llmops.eval_runner --prompt step2_outline --version v2
  python -m services.llmops.eval_runner --all

REGRESSION DETECTION:
  After running, compare scores to baselines in registry.yaml.
  If any metric drops > 5% from baseline → exit code 1 (CI fails).
"""
from __future__ import annotations
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Optional

from services.llmops.judge_evaluator import JudgeEvaluator, EvalResult
from services.llmops.eval_dataset import load_test_cases

logger = logging.getLogger(__name__)

EVAL_DATASET_PATH = Path(__file__).parent.parent.parent.parent.parent / "prompts" / "evals"
MAX_CONCURRENT_EVALS = 10
REGRESSION_THRESHOLD = 0.05


class EvalRunner:
    """Runs batch evaluations for CI and ad-hoc quality checks."""

    def __init__(self):
        self._evaluator = JudgeEvaluator()

    async def run_for_prompt(
        self,
        prompt_name: str,
        version:     Optional[str] = None,
        verbose:     bool = False,
    ) -> dict:
        """
        Run all test cases for a specific prompt.
        Returns dict with pass/fail counts, averages, and regression status.
        """
        test_cases = load_test_cases(prompt_name, EVAL_DATASET_PATH)
        if not test_cases:
            logger.warning(f"No test cases found for prompt '{prompt_name}'")
            return {"passed": 0, "failed": 0, "total": 0, "cases": []}

        logger.info(f"Running {len(test_cases)} test cases for '{prompt_name}'")

        from services.llmops.prompt_registry import get_prompt
        prompt_template = get_prompt(prompt_name)

        semaphore = asyncio.Semaphore(MAX_CONCURRENT_EVALS)

        async def run_one(tc: dict) -> EvalResult:
            async with semaphore:
                try:
                    generated = await self._generate_for_test_case(prompt_template, tc["input"])
                except Exception as e:
                    logger.error(f"Generation failed for test case {tc['id']}: {e}")
                    generated = f"GENERATION_FAILED: {e}"

                return await self._evaluator.evaluate(
                    test_case_id=tc["id"],
                    prompt_name=prompt_name,
                    input_data=tc["input"],
                    generated_output=generated,
                )

        results: list[EvalResult] = await asyncio.gather(
            *[run_one(tc) for tc in test_cases],
            return_exceptions=True,
        )

        valid_results = [r for r in results if isinstance(r, EvalResult)]
        passed = sum(1 for r in valid_results if r.overall_passed)
        failed = len(valid_results) - passed

        avg_faithfulness  = self._avg([r.faithfulness.score for r in valid_results if r.faithfulness])
        avg_schema        = self._avg([r.schema_compliance.score for r in valid_results if r.schema_compliance])
        avg_hallucination = self._avg([r.hallucination.score for r in valid_results if r.hallucination])

        # Regression detection
        baseline            = prompt_template.eval_baseline
        regression_detected = False
        regressions         = []

        if baseline:
            if avg_faithfulness and "faithfulness" in baseline:
                drop = baseline["faithfulness"] - avg_faithfulness
                if drop > REGRESSION_THRESHOLD:
                    regression_detected = True
                    regressions.append(f"faithfulness dropped {drop:.1%}")
            if avg_hallucination and "hallucination_rate" in baseline:
                increase = avg_hallucination - baseline["hallucination_rate"]
                if increase > REGRESSION_THRESHOLD:
                    regression_detected = True
                    regressions.append(f"hallucination_rate increased {increase:.1%}")

        summary = {
            "prompt_name":            prompt_name,
            "prompt_version":         prompt_template.version,
            "total":                  len(valid_results),
            "passed":                 passed,
            "failed":                 failed,
            "pass_rate":              passed / len(valid_results) if valid_results else 0,
            "avg_faithfulness":       avg_faithfulness,
            "avg_schema_compliance":  avg_schema,
            "avg_hallucination":      avg_hallucination,
            "regression_detected":    regression_detected,
            "regressions":            regressions,
            "cases":                  [
                {**r.summary_scores, "test_case_id": r.test_case_id}
                for r in valid_results
            ],
        }

        if verbose:
            for r in valid_results:
                status = "✓ PASS" if r.overall_passed else "✗ FAIL"
                print(f"{status} {r.test_case_id}: {r.summary_scores}")

        return summary

    async def _generate_for_test_case(self, prompt_template, input_data: dict) -> str:
        """Run the actual prompt against a test case input."""
        system = prompt_template.render_system(**input_data)
        user   = prompt_template.render_user(**input_data)

        import openai
        client = openai.AsyncOpenAI()
        from services.llmops.model_router import get_model_for_class
        model = get_model_for_class(prompt_template.model_class)

        response = await client.chat.completions.create(
            model=model,
            max_tokens=prompt_template.max_tokens,
            temperature=prompt_template.temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
        )
        return response.choices[0].message.content or ""

    @staticmethod
    def _avg(scores: list[float]) -> Optional[float]:
        return round(sum(scores) / len(scores), 4) if scores else None


async def main():
    """CLI entry point for CI gate."""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", help="Prompt name to evaluate")
    parser.add_argument("--all", action="store_true", help="Run all prompts")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    runner = EvalRunner()

    if args.all:
        from services.llmops.prompt_registry import get_registry
        registry = get_registry()
        prompts  = [p["name"] for p in registry.list_prompts()
                    if "eval" not in p.get("tags", []) and "judge" not in p["name"]]
    elif args.prompt:
        prompts = [args.prompt]
    else:
        print("Specify --prompt NAME or --all")
        sys.exit(1)

    any_regression = False
    for prompt_name in prompts:
        print(f"\n{'='*60}")
        print(f"Evaluating: {prompt_name}")
        print("=" * 60)
        summary = await runner.run_for_prompt(prompt_name, verbose=args.verbose)
        print(json.dumps(summary, indent=2))
        if summary.get("regression_detected"):
            any_regression = True
            print(f"\n⚠️  REGRESSION DETECTED: {summary['regressions']}")

    sys.exit(1 if any_regression else 0)


if __name__ == "__main__":
    asyncio.run(main())
