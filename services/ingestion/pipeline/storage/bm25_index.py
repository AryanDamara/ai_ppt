"""
BM25 sparse search — persisted to Redis.

WHY BM25 ALONGSIDE VECTORS:
  Dense embeddings excel at semantic similarity:
    "earnings" ≈ "revenue" ≈ "income"  → good for conceptual queries

  BM25 excels at exact term matching:
    "EBITDA" ≠ "earnings"    → BM25 correctly distinguishes technical terms
    "$4.2M" exact number     → BM25 finds the precise figure
    "Product SKU-XR7B"       → BM25 matches the exact product code
    Company names, acronyms  → BM25 never confuses "AAPL" with "Apple"

  Together: hybrid search achieves better recall AND precision than either alone.

PERSISTENCE STRATEGY:
  BM25Okapi is serialised with pickle to Redis.
  Corpus (chunk_ids list) stored as JSON alongside.
  TTL: 30 days. Rebuilt from scratch when new documents added to the tenant.
  Keys: bm25:{tenant_id} and bm25:corpus:{tenant_id}

INCREMENTAL UPDATE:
  When a new document is added, we fetch the existing corpus chunk_ids from Redis,
  append the new ones, and rebuild the BM25 index from all stored chunk texts.
  For this to work, chunk texts must also be stored (in Pinecone metadata or
  PostgreSQL). The orchestrator handles this coordination.

THREAD SAFETY:
  BM25Okapi.get_scores() is read-only after building. Safe for concurrent queries.
"""
from __future__ import annotations
import json
import logging
import pickle
from typing import Optional

from core.config import get_settings

settings = get_settings()
logger   = logging.getLogger(__name__)

_BM25_TTL  = 30 * 24 * 3600   # 30 days
_KEY_MODEL  = "bm25:{tenant_id}"
_KEY_CORPUS = "bm25:corpus:{tenant_id}"
_KEY_TEXTS  = "bm25:texts:{tenant_id}"   # Stored chunk texts for rebuild


def _redis():
    import redis
    return redis.Redis.from_url(settings.redis_url, decode_responses=False)


def build_and_save_bm25(
    chunk_texts: list[str],
    chunk_ids:   list[str],
    tenant_id:   str,
) -> None:
    """
    Build BM25 index from scratch and persist to Redis.
    Called by orchestrator after each ingestion job.
    If existing corpus exists in Redis, load + merge before rebuilding.
    """
    from rank_bm25 import BM25Okapi

    r = _redis()

    # Load existing corpus if present
    existing_ids_raw   = r.get(_KEY_CORPUS.format(tenant_id=tenant_id))
    existing_texts_raw = r.get(_KEY_TEXTS.format(tenant_id=tenant_id))

    all_ids   = json.loads(existing_ids_raw) if existing_ids_raw else []
    all_texts = json.loads(existing_texts_raw) if existing_texts_raw else []

    # Append new (dedup by chunk_id)
    existing_id_set = set(all_ids)
    for cid, ctxt in zip(chunk_ids, chunk_texts):
        if cid not in existing_id_set:
            all_ids.append(cid)
            all_texts.append(ctxt)
            existing_id_set.add(cid)

    # Rebuild BM25 from all texts
    tokenized = [t.lower().split() for t in all_texts]
    bm25 = BM25Okapi(tokenized)

    try:
        r.set(_KEY_MODEL.format(tenant_id=tenant_id),  pickle.dumps(bm25),        ex=_BM25_TTL)
        r.set(_KEY_CORPUS.format(tenant_id=tenant_id), json.dumps(all_ids),        ex=_BM25_TTL)
        r.set(_KEY_TEXTS.format(tenant_id=tenant_id),  json.dumps(all_texts),      ex=_BM25_TTL)
        logger.info(f"BM25 index saved: {len(all_ids)} total chunks for tenant {tenant_id[:8]}…")
    except Exception as e:
        logger.error(f"BM25 Redis save failed: {e}")


def bm25_search(
    query:     str,
    tenant_id: str,
    top_k:     int = 20,
) -> list[tuple[str, float]]:
    """
    BM25 search. Returns list of (chunk_id, normalised_score) tuples,
    sorted by score descending. Empty list if index unavailable.

    Scores are normalised to [0, 1] by dividing by max score in results.
    This makes BM25 scores comparable to cosine similarity scores in RRF.
    """
    from rank_bm25 import BM25Okapi

    r = _redis()
    try:
        bm25_bytes  = r.get(_KEY_MODEL.format(tenant_id=tenant_id))
        corpus_raw  = r.get(_KEY_CORPUS.format(tenant_id=tenant_id))
        if not bm25_bytes or not corpus_raw:
            return []

        bm25      = pickle.loads(bm25_bytes)
        chunk_ids = json.loads(corpus_raw)

        tokenized_query = query.lower().split()
        scores          = bm25.get_scores(tokenized_query)

        # Normalise scores
        max_score = max(scores) if len(scores) > 0 and max(scores) > 0 else 1.0
        normalised = [s / max_score for s in scores]

        # Pair and sort
        paired = sorted(
            zip(chunk_ids, normalised),
            key=lambda x: x[1],
            reverse=True,
        )
        return [(cid, score) for cid, score in paired[:top_k] if score > 0]

    except Exception as e:
        logger.error(f"BM25 search failed: {e}")
        return []
