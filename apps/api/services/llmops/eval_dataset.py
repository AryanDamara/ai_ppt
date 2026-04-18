"""
Evaluation dataset management — test cases for LLM-as-Judge.

Test cases are stored in prompts/evals/test_cases.json.
Each test case has: id, prompt_name, input, expected_properties.
"""
from __future__ import annotations
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_test_cases(prompt_name: str, dataset_dir: Path) -> list[dict]:
    """
    Load test cases for a specific prompt from the eval dataset.
    File: prompts/evals/test_cases.json
    Filters by prompt_name field.
    """
    test_cases_file = dataset_dir / "test_cases.json"
    if not test_cases_file.exists():
        logger.warning(f"Test cases file not found: {test_cases_file}")
        return []

    try:
        with open(test_cases_file) as f:
            all_cases = json.load(f)

        cases = [tc for tc in all_cases if tc.get("prompt_name") == prompt_name]
        if not cases:
            logger.warning(f"No test cases found for prompt '{prompt_name}'")
        else:
            logger.info(f"Loaded {len(cases)} test cases for '{prompt_name}'")
        return cases

    except Exception as e:
        logger.error(f"Failed to load test cases: {e}")
        return []


def create_minimal_test_dataset() -> list[dict]:
    """
    Generate a minimal set of 50 test cases covering all prompt types.
    Used for initial setup — engineers should add real test cases after.
    """
    industries = [
        "technology", "financial_services", "healthcare", "manufacturing",
        "retail", "government", "legal", "education",
    ]
    durations  = [5, 10, 20]
    frameworks = ["pyramid_principle", "problem_solution", "chronological"]

    prompts_2 = [
        "Q3 2024 financial results and outlook",
        "Product roadmap for next 18 months",
        "Competitive analysis and market positioning",
        "Digital transformation strategy proposal",
        "Annual board review and governance update",
        "Market entry strategy for Southeast Asia",
        "Cost reduction initiative findings",
        "Customer satisfaction and NPS analysis",
        "M&A integration progress update",
        "Supply chain resilience assessment",
    ]

    cases = []
    case_num = 1

    for prompt_text in prompts_2:
        for industry in industries[:3]:
            for duration in durations:
                cases.append({
                    "id": f"tc_step2_{case_num:03d}",
                    "prompt_name": "step2_outline",
                    "input": {
                        "user_prompt": prompt_text,
                        "industry": industry,
                        "audience": "executives",
                        "duration_minutes": duration,
                        "narrative_framework": frameworks[case_num % len(frameworks)],
                        "theme": "corporate_dark",
                        "rag_context_section": "",
                    },
                    "expected_properties": [
                        f"slides count appropriate for {duration} minutes",
                        "all action_titles <= 60 chars",
                        "first slide is title_slide or section_divider",
                    ],
                })
                case_num += 1
                if case_num > 50:
                    break
            if case_num > 50:
                break
        if case_num > 50:
            break

    return cases[:50]
