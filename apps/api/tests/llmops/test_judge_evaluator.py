"""Tests for the LLM-as-Judge evaluator data structures."""
import pytest


def test_judge_result_passed_faithfulness():
    """JudgeResult for faithfulness should pass if score >= threshold."""
    from services.llmops.judge_evaluator import JudgeResult, FAITHFULNESS_MIN

    result = JudgeResult(judge_name="faithfulness", score=0.90, reasoning="Good match")
    assert result.passed is True

    result2 = JudgeResult(judge_name="faithfulness", score=0.50, reasoning="Poor match")
    assert result2.passed is False


def test_judge_result_passed_hallucination():
    """JudgeResult for hallucination should be inverted (lower = better)."""
    from services.llmops.judge_evaluator import JudgeResult, HALLUCINATION_MAX

    # Low hallucination score = PASS
    result = JudgeResult(judge_name="hallucination", score=0.05, reasoning="Clean")
    assert result.passed is True

    # High hallucination score = FAIL
    result2 = JudgeResult(judge_name="hallucination", score=0.80, reasoning="Fabrications found")
    assert result2.passed is False


def test_judge_result_passed_schema():
    """JudgeResult for schema compliance should pass if score >= 0.90."""
    from services.llmops.judge_evaluator import JudgeResult, SCHEMA_COMPLIANCE_MIN

    result = JudgeResult(judge_name="schema_compliance", score=0.95, reasoning="Compliant")
    assert result.passed is True

    result2 = JudgeResult(judge_name="schema_compliance", score=0.60, reasoning="Multiple violations")
    assert result2.passed is False


def test_eval_result_overall():
    """EvalResult.overall_passed should require all judges to pass."""
    from services.llmops.judge_evaluator import EvalResult, JudgeResult

    result = EvalResult(
        test_case_id="tc_001",
        prompt_name="step2_outline",
        prompt_version="v1",
        input_data={"user_prompt": "test"},
        generated_output="{}",
        faithfulness=JudgeResult("faithfulness", 0.90, "Good"),
        schema_compliance=JudgeResult("schema_compliance", 0.95, "Good"),
        hallucination=JudgeResult("hallucination", 0.10, "Clean"),
    )
    assert result.overall_passed is True

    # One failing judge → overall fail
    result2 = EvalResult(
        test_case_id="tc_002",
        prompt_name="step2_outline",
        prompt_version="v1",
        input_data={"user_prompt": "test"},
        generated_output="{}",
        faithfulness=JudgeResult("faithfulness", 0.40, "Bad"),
        schema_compliance=JudgeResult("schema_compliance", 0.95, "Good"),
        hallucination=JudgeResult("hallucination", 0.10, "Clean"),
    )
    assert result2.overall_passed is False


def test_eval_result_summary_scores():
    """summary_scores should return all judge scores."""
    from services.llmops.judge_evaluator import EvalResult, JudgeResult

    result = EvalResult(
        test_case_id="tc_001",
        prompt_name="test",
        prompt_version="v1",
        input_data={},
        generated_output="",
        faithfulness=JudgeResult("faithfulness", 0.85, "OK"),
        schema_compliance=JudgeResult("schema_compliance", 0.92, "OK"),
    )

    scores = result.summary_scores
    assert scores["faithfulness"] == 0.85
    assert scores["schema_compliance"] == 0.92
    assert scores["hallucination"] is None  # Not run


def test_complexity_scorer():
    """TaskComplexityScorer should score based on prompt characteristics."""
    from services.llmops.complexity_scorer import TaskComplexityScorer

    scorer = TaskComplexityScorer()

    simple = scorer.score("Create a simple intro deck", slide_count_estimate=5)
    assert simple["recommended_class"] in ("fast", "balanced")
    assert simple["complexity_score"] < 0.5

    complex_result = scorer.score(
        "Analyze the EBITDA margins and CAGR across all portfolio companies " * 5,
        slide_count_estimate=25,
        has_rag_context=True,
        language="de-DE",
    )
    assert complex_result["recommended_class"] == "powerful"
    assert complex_result["complexity_score"] >= 0.5
