"""
Semantic cache — Redis-backed semantic similarity cache for LLM responses.

This is the Phase 5 upgrade that lives alongside the Phase 1 PostgreSQL cache.
The Phase 1 cache (services/cache/semantic_cache.py) continues to work.
This cache is used by LLMOps modules for step-level response caching.

Threshold: cosine similarity >= 0.92 → cache hit.
Cost savings: 15-30% for repeat/similar requests.
"""
from __future__ import annotations
import hashlib
import json
import logging
import pickle
import time
from typing import Optional, Any

logger = logging.getLogger(__name__)


class SemanticCache:
    """
    Redis-backed semantic similarity cache for LLM responses.
    Threshold: cosine similarity >= 0.92 → cache hit.
    """

    SIMILARITY_THRESHOLD = 0.92
    DEFAULT_TTL          = 3600   # 1 hour

    def __init__(self):
        self._redis  = None
        self._oai    = None

    def _get_redis(self):
        if self._redis is None:
            import redis
            import os
            self._redis = redis.Redis.from_url(
                os.getenv("REDIS_URL", "redis://localhost:6379"),
                decode_responses=False,
            )
        return self._redis

    def _get_oai(self):
        if self._oai is None:
            import openai
            import os
            self._oai = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        return self._oai

    def _embed_query(self, query: str) -> list[float]:
        """Embed a cache key for semantic comparison."""
        try:
            resp = self._get_oai().embeddings.create(
                model="text-embedding-3-small",
                input=query[:1000],
            )
            return resp.data[0].embedding
        except Exception as e:
            logger.warning(f"Cache embedding failed: {e}")
            return []

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two embedding vectors."""
        if not a or not b or len(a) != len(b):
            return 0.0
        dot   = sum(x * y for x, y in zip(a, b))
        mag_a = sum(x ** 2 for x in a) ** 0.5
        mag_b = sum(x ** 2 for x in b) ** 0.5
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)

    async def get(self, key: str) -> Optional[Any]:
        """
        Check semantic cache for a key.
        Returns cached value if similarity >= threshold, else None.
        """
        try:
            r         = self._get_redis()
            query_emb = self._embed_query(key)
            if not query_emb:
                return None

            namespace = "semantic:llmops"
            entries   = r.hgetall(f"cache:{namespace}")

            best_sim   = 0.0
            best_value = None

            for hash_key, raw in entries.items():
                try:
                    entry = pickle.loads(raw)
                    sim   = self._cosine_similarity(query_emb, entry["embedding"])
                    if sim > best_sim:
                        best_sim   = sim
                        best_value = entry["value"]
                except Exception:
                    continue

            if best_sim >= self.SIMILARITY_THRESHOLD:
                logger.info(f"Semantic cache HIT (similarity={best_sim:.3f})")
                return best_value

            return None

        except Exception as e:
            logger.warning(f"Semantic cache get failed: {e}")
            return None

    async def set(self, key: str, value: Any, ttl_seconds: int = DEFAULT_TTL) -> None:
        """Store a value in the semantic cache."""
        try:
            r         = self._get_redis()
            query_emb = self._embed_query(key)
            if not query_emb:
                return

            key_hash  = hashlib.sha256(key.encode()).hexdigest()[:16]
            namespace = "semantic:llmops"

            entry = {
                "embedding":  query_emb,
                "value":      value,
                "created_at": time.time(),
                "key":        key[:200],
            }

            r.hset(f"cache:{namespace}", key_hash, pickle.dumps(entry))
            r.expire(f"cache:{namespace}", ttl_seconds)

            logger.debug(f"Semantic cache SET: {key[:50]}…")

        except Exception as e:
            logger.warning(f"Semantic cache set failed: {e}")
