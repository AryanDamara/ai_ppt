"""
Metadata enricher — micro-summary + keyword tagging per chunk.

WHAT THIS DOES:
  After chunking and PII redaction, each chunk gets enriched with:
  1. A micro-summary (1-2 sentences) optimised for search results display
  2. Keyword tags extracted from the chunk text (used for BM25 boost)
  3. Topic classification (e.g., "financial", "technical", "strategic")

WHY:
  - Micro-summaries improve retrieval result presentation in the UI
  - Keywords boost BM25 search accuracy for technical terms
  - Topic classification enables filtering by content type

IMPLEMENTATION:
  Uses tiktoken-based keyword extraction (no LLM call needed for keywords)
  and optional GPT-4o-mini for micro-summaries when enabled.
  Keywords use TF-based ranking within the chunk to surface domain terms.

COST CONTROL:
  - Keyword extraction is pure Python — zero API cost
  - Micro-summaries use GPT-4o-mini (~$0.15/1M tokens) and are optional
  - Batch summarisation: up to 10 chunks per API call
"""
from __future__ import annotations
import logging
import re
from collections import Counter
from typing import Optional

from core.config import get_settings

settings = get_settings()
logger   = logging.getLogger(__name__)

# Common English stopwords to filter out of keyword extraction
_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "it", "was", "be", "are", "been",
    "has", "had", "have", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "this", "that", "these",
    "those", "not", "no", "if", "then", "than", "when", "where", "what",
    "which", "who", "whom", "how", "all", "each", "every", "both",
    "few", "more", "most", "other", "some", "such", "only", "own",
    "same", "so", "very", "just", "about", "above", "after", "again",
    "also", "any", "as", "because", "before", "between", "during",
    "here", "into", "its", "new", "now", "our", "over", "their",
    "there", "through", "under", "up", "we", "were", "your", "you",
})

# Word pattern for keyword extraction (letters, digits, hyphens)
_WORD_PATTERN = re.compile(r'\b[a-zA-Z][a-zA-Z0-9\-]{2,}\b')


def extract_keywords(
    text: str,
    max_keywords: int = 10,
    min_word_length: int = 3,
) -> list[str]:
    """
    Extract the most important keywords from a chunk of text.

    Uses term frequency ranking with stopword filtering.
    No API calls — pure Python, <1ms per chunk.

    Parameters
    ----------
    text : chunk text to extract keywords from
    max_keywords : maximum number of keywords to return
    min_word_length : minimum word length to consider

    Returns
    -------
    List of keywords ordered by relevance (most relevant first)
    """
    if not text or len(text) < 10:
        return []

    # Tokenise and filter
    words = _WORD_PATTERN.findall(text.lower())
    words = [
        w for w in words
        if w not in _STOPWORDS
        and len(w) >= min_word_length
        and not w.isdigit()
    ]

    if not words:
        return []

    # Count term frequency
    counts = Counter(words)

    # Boost multi-word technical terms (bigrams)
    lower_text = text.lower()
    bigram_boosts = _extract_bigrams(lower_text)
    for bigram, count in bigram_boosts.items():
        counts[bigram] = count * 3   # Boost bigrams

    # Return top keywords
    return [word for word, _ in counts.most_common(max_keywords)]


def _extract_bigrams(text: str) -> Counter:
    """
    Extract meaningful bigrams (two-word phrases) from text.
    Filters stopword-only bigrams.
    """
    words = _WORD_PATTERN.findall(text)
    bigrams = Counter()
    for i in range(len(words) - 1):
        w1, w2 = words[i], words[i + 1]
        if w1 not in _STOPWORDS and w2 not in _STOPWORDS:
            if len(w1) >= 3 and len(w2) >= 3:
                bigrams[f"{w1} {w2}"] += 1
    return bigrams


def classify_topic(text: str) -> str:
    """
    Classify chunk text into a broad topic category.

    Uses keyword matching — no API call.
    Categories: financial, technical, strategic, operational, legal, general

    Returns
    -------
    Topic string (lowercase)
    """
    if not text:
        return "general"

    lower = text.lower()

    topic_signals = {
        "financial": [
            "revenue", "profit", "ebitda", "margin", "earnings",
            "dividend", "cash flow", "fiscal", "quarter", "annual",
            "growth rate", "year-over-year", "yoy", "qoq",
            "balance sheet", "income statement", "assets", "liabilities",
            "$", "million", "billion",
        ],
        "technical": [
            "api", "database", "algorithm", "architecture", "deployment",
            "infrastructure", "scalability", "latency", "throughput",
            "microservice", "kubernetes", "docker", "cloud", "aws",
            "machine learning", "neural network", "model", "pipeline",
        ],
        "strategic": [
            "strategy", "roadmap", "vision", "mission", "objective",
            "competitive", "market share", "positioning", "differentiation",
            "target market", "expansion", "acquisition", "partnership",
            "innovation", "transformation",
        ],
        "operational": [
            "process", "workflow", "efficiency", "automation",
            "kpi", "metric", "target", "milestone", "timeline",
            "resource", "capacity", "utilization", "supply chain",
        ],
        "legal": [
            "compliance", "regulation", "gdpr", "hipaa", "contract",
            "liability", "indemnity", "jurisdiction", "intellectual property",
            "patent", "trademark", "confidential", "non-disclosure",
        ],
    }

    scores: dict[str, int] = {}
    for topic, keywords in topic_signals.items():
        score = sum(1 for kw in keywords if kw in lower)
        if score > 0:
            scores[topic] = score

    if not scores:
        return "general"

    return max(scores, key=scores.get)


async def generate_micro_summaries(
    texts: list[str],
    max_summary_length: int = 100,
) -> list[str]:
    """
    Generate brief micro-summaries for a batch of chunks using GPT-4o-mini.

    Parameters
    ----------
    texts : list of chunk texts to summarise
    max_summary_length : max character length per summary

    Returns
    -------
    List of summary strings (same order as input)
    Falls back to first-sentence extraction if API call fails.
    """
    if not texts:
        return []

    # Fast fallback: extract first sentence
    fallback_summaries = [_first_sentence(t, max_summary_length) for t in texts]

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key)

        # Batch: up to 10 texts per call
        summaries = []
        for i in range(0, len(texts), 10):
            batch = texts[i:i+10]
            batch_text = "\n\n---\n\n".join(
                f"[Chunk {j+1}]: {t[:500]}" for j, t in enumerate(batch)
            )

            response = await client.chat.completions.create(
                model=settings.openai_metadata_model,
                temperature=0.1,
                max_tokens=200 * len(batch),
                timeout=30,
                messages=[{
                    "role": "system",
                    "content": (
                        "Generate a 1-sentence micro-summary for each chunk below. "
                        "Each summary should capture the key point in under 100 characters. "
                        "Return one summary per line, prefixed with [Chunk N]: "
                    ),
                }, {
                    "role": "user",
                    "content": batch_text,
                }],
            )

            result = response.choices[0].message.content or ""
            lines  = [l.strip() for l in result.strip().split("\n") if l.strip()]

            for j, text in enumerate(batch):
                if j < len(lines):
                    # Strip the "[Chunk N]: " prefix
                    summary = lines[j]
                    if "]: " in summary:
                        summary = summary.split("]: ", 1)[1]
                    summaries.append(summary[:max_summary_length])
                else:
                    summaries.append(fallback_summaries[i + j])

        return summaries

    except Exception as e:
        logger.warning(f"Micro-summary generation failed: {e}. Using first-sentence fallback.")
        return fallback_summaries


def _first_sentence(text: str, max_length: int = 100) -> str:
    """Extract the first sentence from text as a fallback summary."""
    if not text:
        return ""
    # Find first sentence boundary
    for end_char in [". ", "! ", "? ", ".\n", "!\n", "?\n"]:
        idx = text.find(end_char)
        if 10 < idx < max_length:
            return text[:idx + 1].strip()
    # No sentence boundary found — truncate
    return text[:max_length].rstrip() + ("…" if len(text) > max_length else "")
