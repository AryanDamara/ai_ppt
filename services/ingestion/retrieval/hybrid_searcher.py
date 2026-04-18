"""
Hybrid searcher — parallel dense + sparse search fused with Reciprocal Rank Fusion.

ALGORITHM: Reciprocal Rank Fusion (RRF)
  For each document, compute: score = Σ 1/(k + rank_i) across all result lists.
  k=60 is the standard smoothing constant (prevents very high ranks from dominating).

  WHY RRF OVER LINEAR COMBINATION:
    Linear: score = α × cosine + β × bm25
    Problem: BM25 scores in [0, 30], cosine in [0, 1] — different scales.
    Calibrating α and β requires tuning for each domain.

    RRF: rank-based, scale-invariant.
    A document at rank 1 in dense + rank 3 in BM25 beats one at rank 2 in dense + not in BM25.
    No tuning required. Works consistently across domains and query types.

FLOW:
  1. Embed query (async, same model as ingestion)
  2. Dense search (Pinecone) and BM25 search run in PARALLEL with asyncio.gather
  3. RRF fusion on the two ranked lists
  4. Confidence threshold filter (dense_score < min_relevance_score → discard)
  5. Return top_k_initial candidates to reranker
"""
from __future__ import annotations
import asyncio
import logging
from typing import Optional

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from pipeline.chunk_model import RetrievedChunk
from pipeline.storage.pinecone_client import PineconeVectorStore
from pipeline.storage.bm25_index import bm25_search
from core.config import get_settings
from core.exceptions import RetrievalError

settings = get_settings()
logger   = logging.getLogger(__name__)

_RRF_K = 60


class HybridSearcher:

    def __init__(self):
        self._pinecone = PineconeVectorStore()
        self._oai      = AsyncOpenAI(api_key=settings.openai_api_key)

    async def search(
        self,
        query:          str,
        tenant_id:      str,
        top_k_initial:  int            = None,
        doc_ids_filter: list[str]      | None = None,
    ) -> list[RetrievedChunk]:
        """
        Execute hybrid search and return RRF-fused results.

        Parameters
        ----------
        query : slide topic or retrieval query string
        tenant_id : authenticated tenant for namespace isolation
        top_k_initial : candidates to return for reranking
        doc_ids_filter : restrict to specific document IDs (user-selected docs)

        Returns
        -------
        list[RetrievedChunk] sorted by fused_score descending
        """
        top_k = top_k_initial or settings.retrieval_top_k_initial

        # Embed query
        query_emb = await self._embed_query(query)

        # Dense + sparse in parallel
        dense_task  = asyncio.create_task(
            self._run_dense(query_emb, tenant_id, top_k, doc_ids_filter)
        )
        sparse_task = asyncio.create_task(
            self._run_sparse(query, tenant_id, top_k)
        )

        dense_results, sparse_results = await asyncio.gather(
            dense_task, sparse_task, return_exceptions=True
        )

        if isinstance(dense_results, Exception):
            logger.error(f"Dense search error: {dense_results}")
            dense_results = []
        if isinstance(sparse_results, Exception):
            logger.error(f"BM25 search error: {sparse_results}")
            sparse_results = []

        # RRF fusion
        fused = self._rrf(dense_results, sparse_results, top_k)

        # Confidence threshold: only apply to chunks that came from dense search
        filtered = []
        for chunk in fused:
            if chunk.dense_score > 0 and chunk.dense_score < settings.min_relevance_score:
                continue
            filtered.append(chunk)

        logger.info(
            f"Hybrid search '{query[:40]}…': "
            f"{len(dense_results)} dense + {len(sparse_results)} sparse "
            f"→ {len(fused)} fused → {len(filtered)} after threshold"
        )
        return filtered

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    async def _embed_query(self, query: str) -> list[float]:
        resp = await self._oai.embeddings.create(
            model=settings.openai_embedding_model,
            input=query,
        )
        return resp.data[0].embedding

    async def _run_dense(
        self,
        emb:       list[float],
        tenant_id: str,
        top_k:     int,
        doc_filter: list[str] | None,
    ) -> list[RetrievedChunk]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._pinecone.dense_search(emb, tenant_id, top_k, doc_filter)
        )

    async def _run_sparse(
        self,
        query:     str,
        tenant_id: str,
        top_k:     int,
    ) -> list[tuple[str, float]]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: bm25_search(query, tenant_id, top_k)
        )

    def _rrf(
        self,
        dense:  list[RetrievedChunk],
        sparse: list[tuple[str, float]],
        top_k:  int,
    ) -> list[RetrievedChunk]:
        """Reciprocal Rank Fusion of dense and sparse result lists."""
        rrf_scores: dict[str, float] = {}

        # Dense ranking contribution
        for rank, chunk in enumerate(
            sorted(dense, key=lambda c: c.dense_score, reverse=True)
        ):
            rrf_scores[chunk.chunk_id] = (
                rrf_scores.get(chunk.chunk_id, 0.0) + 1.0 / (_RRF_K + rank + 1)
            )

        # Sparse ranking contribution
        for rank, (chunk_id, _bm25_score) in enumerate(sparse):
            rrf_scores[chunk_id] = (
                rrf_scores.get(chunk_id, 0.0) + 1.0 / (_RRF_K + rank + 1)
            )

        dense_by_id   = {c.chunk_id: c for c in dense}
        sparse_by_id  = {cid: score for cid, score in sparse}

        merged: list[RetrievedChunk] = []
        for chunk_id, fused_score in sorted(
            rrf_scores.items(), key=lambda x: x[1], reverse=True
        )[:top_k]:
            if chunk_id in dense_by_id:
                chunk              = dense_by_id[chunk_id]
                chunk.fused_score  = fused_score
                chunk.sparse_score = sparse_by_id.get(chunk_id, 0.0)
                merged.append(chunk)
            # BM25-only results: skip if no text available from dense search
            # In a full implementation, fetch text from PostgreSQL by chunk_id

        return merged
