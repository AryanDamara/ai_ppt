"""
Task complexity scorer — scores task complexity to inform model routing.

Uses heuristics based on prompt characteristics, not an LLM call.
Zero cost, sub-millisecond execution.
"""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)


class TaskComplexityScorer:
    """
    Scores task complexity to inform model routing.
    Builds on prompt-defined model_class but can override based on content.
    """

    def score(
        self,
        user_prompt: str,
        slide_count_estimate: int = 10,
        has_rag_context: bool = False,
        language: str = "en",
    ) -> dict:
        """
        Score the complexity of a generation task.

        Returns dict with:
          complexity_score : 0-1 (0=simple, 1=very complex)
          recommended_class : "fast" | "balanced" | "powerful"
          reasoning : explanation of the routing decision
        """
        score = 0.0
        factors = []

        # Prompt length: longer = more complex
        prompt_words = len(user_prompt.split())
        if prompt_words > 200:
            score += 0.3
            factors.append(f"Long prompt ({prompt_words} words)")
        elif prompt_words > 50:
            score += 0.1

        # Slide count
        if slide_count_estimate > 20:
            score += 0.2
            factors.append(f"Large deck ({slide_count_estimate} slides)")
        elif slide_count_estimate > 10:
            score += 0.1

        # RAG context (more context = more complex synthesis needed)
        if has_rag_context:
            score += 0.3
            factors.append("RAG-grounded (needs accurate synthesis)")

        # Technical/financial keywords
        tech_keywords = [
            "roi", "ebitda", "cagr", "npv", "irr", "discounted",
            "regression", "algorithm", "architecture", "integration",
            "derivatives", "hedging", "arbitrage",
        ]
        found = [kw for kw in tech_keywords if kw in user_prompt.lower()]
        if found:
            score += 0.2
            factors.append(f"Technical content: {found[:3]}")

        # Non-English
        if language not in ("en", "en-US", "en-GB"):
            score += 0.1
            factors.append(f"Non-English: {language}")

        score = min(1.0, score)

        if score >= 0.5:
            recommended_class = "powerful"
        elif score >= 0.2:
            recommended_class = "balanced"
        else:
            recommended_class = "fast"

        return {
            "complexity_score":    round(score, 2),
            "recommended_class":   recommended_class,
            "reasoning":           "; ".join(factors) if factors else "Simple task",
        }
