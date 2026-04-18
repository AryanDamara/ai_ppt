"""
Batch embedder — OpenAI text-embedding-3-small in batches of 100.

WHY BATCHING IS NON-NEGOTIABLE:
  A typical 50-page annual report produces ~400 chunks.
  Embedding one-by-one: 400 × ~120ms/call = 48 seconds (unacceptable).
  Embedding in batches of 100: 4 × ~200ms/call = 0.8 seconds (production-ready).

DIMENSION VALIDATION:
  After every batch, assert len(embedding) == pinecone_dimension (1536).
  If a different model is accidentally configured, we detect it immediately
  instead of silently corrupting the Pinecone index with wrong-dimension vectors.
  Mixed-dimension vectors in an index produce silent wrong results.

RETRY STRATEGY:
  3 retries with exponential backoff (2s, 4s, 8s).
  On permanent failure, raise EmbeddingFailedError — orchestrator pushes to DLQ.
"""
from __future__ import annotations
import asyncio
import logging

from tenacity import retry, stop_after_attempt, wait_exponential

from pipeline.chunk_model import Chunk
from core.config import get_settings
from core.exceptions import EmbeddingFailedError

settings = get_settings()
logger   = logging.getLogger(__name__)

BATCH_SIZE = 100   # OpenAI allows up to 2048 per call; 100 is safe and efficient


class BatchEmbedder:

    def __init__(self):
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def embed_chunks(self, chunks: list[Chunk]) -> list[Chunk]:
        """
        Embed all chunks in batches. Populates chunk.embedding in-place.

        Parameters
        ----------
        chunks : list of Chunk objects with text populated (pre-PII-redacted)

        Returns
        -------
        Same list with chunk.embedding populated (list[float], dim=1536)

        Raises
        ------
        EmbeddingFailedError if any batch fails after all retries
        """
        if not chunks:
            return chunks

        total   = len(chunks)
        batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
        logger.info(f"Embedding {total} chunks in {batches} batches")

        for batch_num, start in enumerate(range(0, total, BATCH_SIZE)):
            batch  = chunks[start: start + BATCH_SIZE]
            texts  = [c.text for c in batch]

            embeddings = await self._embed_batch_with_retry(texts, batch_num)

            for chunk, emb in zip(batch, embeddings):
                # Dimension validation — catches wrong model config immediately
                if len(emb) != settings.pinecone_dimension:
                    raise EmbeddingFailedError(
                        f"Embedding dimension mismatch: expected {settings.pinecone_dimension}, "
                        f"got {len(emb)}. Check openai_embedding_model config. "
                        f"Current model: {settings.openai_embedding_model}"
                    )
                chunk.embedding = emb
                chunk.metadata.token_count = len(chunk.text.split())  # approximate

            logger.debug(f"Batch {batch_num + 1}/{batches} embedded")

        return chunks

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=20),
        reraise=True,
    )
    async def _embed_batch_with_retry(
        self,
        texts:     list[str],
        batch_num: int,
    ) -> list[list[float]]:
        """Embed one batch. Retried on transient API errors."""
        try:
            response = await self._client.embeddings.create(
                model=settings.openai_embedding_model,
                input=texts,
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            logger.error(f"Embedding batch {batch_num} failed: {e}")
            raise EmbeddingFailedError(f"Batch {batch_num} failed: {e}") from e
