"""
Cross-encoder reranker — final relevance scoring.

WHY RERANKING AFTER HYBRID SEARCH:
  Initial retrieval (dense + sparse) optimises for RECALL: retrieve everything
  that might be relevant. Fast because it uses pre-computed vectors.

  Reranking optimises for PRECISION: from the top-20 candidates, find the
  top-8 that are most relevant to the specific query. Accurate because the
  cross-encoder reads both query and document simultaneously (not independently).

  Cross-encoder accuracy: NDCG@10 ~0.72 (vs. ~0.58 for bi-encoder alone).
  Cost: ~50ms for 20 pairs on a CPU. Acceptable for retrieval.

MODEL: BAAI/bge-reranker-large
  - 560M parameters
  - Trained on MS MARCO + BEIR benchmark
  - Outperforms ms-marco-MiniLM on financial/technical text
  - ~1.4GB memory footprint

FALLBACK:
  If model unavailable (first startup, memory constraint), fall back to
  fused_score ordering from RRF. No crash, slightly lower precision.

LOADING:
  Model loaded ONCE at first call and kept in memory.
  Load time: ~4 seconds. Query time: ~30-80ms for 20 pairs on CPU.
"""
from __future__ import annotations
import asyncio
import logging
from typing import Optional

from pipeline.chunk_model import RetrievedChunk
from core.config import get_settings

settings = get_settings()
logger   = logging.getLogger(__name__)

_MODEL = None


def _load_model():
    global _MODEL
    if _MODEL is None:
        try:
            from sentence_transformers import CrossEncoder
            logger.info(f"Loading reranker: {settings.reranker_model}")
            _MODEL = CrossEncoder(settings.reranker_model)
            logger.info("Reranker loaded")
        except Exception as e:
            logger.error(f"Reranker load failed: {e}. Falling back to RRF ordering.")
    return _MODEL


class CrossEncoderReranker:

    async def rerank(
        self,
        query:  str,
        chunks: list[RetrievedChunk],
        top_k:  int | None = None,
    ) -> list[RetrievedChunk]:
        """
        Rerank candidates and return the top_k most relevant chunks.

        Parameters
        ----------
        query : original retrieval query
        chunks : candidates from hybrid search (already RRF-fused and thresholded)
        top_k : how many to return (default: settings.retrieval_top_k_final)

        Returns
        -------
        list[RetrievedChunk] sorted by rerank_score descending, length <= top_k
        """
        final_k = top_k or settings.retrieval_top_k_final

        if not chunks:
            return []

        model = _load_model()
        if model is None:
            logger.warning("Reranker unavailable — using RRF fused_score ordering")
            return sorted(chunks, key=lambda c: c.fused_score, reverse=True)[:final_k]

        try:
            pairs = [(query, c.text) for c in chunks]
            loop  = asyncio.get_event_loop()

            # Run in executor — cross-encoder predict() is CPU-bound
            scores = await loop.run_in_executor(
                None,
                lambda: model.predict(pairs, show_progress_bar=False)
            )

            for chunk, score in zip(chunks, scores):
                chunk.rerank_score = float(score)

            reranked = sorted(chunks, key=lambda c: c.rerank_score, reverse=True)

            if reranked:
                logger.info(
                    f"Reranked {len(chunks)} → top {final_k}. "
                    f"Top score: {reranked[0].rerank_score:.3f}, "
                    f"Bottom: {reranked[min(final_k-1, len(reranked)-1)].rerank_score:.3f}"
                )

            return reranked[:final_k]

        except Exception as e:
            logger.error(f"Reranking failed: {e}. Falling back to fused_score.")
            return sorted(chunks, key=lambda c: c.fused_score, reverse=True)[:final_k]
