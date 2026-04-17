import hashlib
import json
import numpy as np
from typing import Optional
from datetime import datetime, timezone, timedelta

from openai import AsyncOpenAI
from core.config import get_settings
from core.logging import get_logger

settings = get_settings()
client = AsyncOpenAI(api_key=settings.openai_api_key)
logger = get_logger(__name__)


def normalize_prompt(prompt: str) -> str:
    return " ".join(prompt.lower().split())


def cosine_similarity(a: list[float], b: list[float]) -> float:
    a_arr = np.array(a, dtype=np.float64)
    b_arr = np.array(b, dtype=np.float64)
    norm_a = np.linalg.norm(a_arr)
    norm_b = np.linalg.norm(b_arr)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a_arr, b_arr) / (norm_a * norm_b))


async def get_embedding(text: str) -> list[float]:
    response = await client.embeddings.create(
        model=settings.openai_embedding_model,
        input=normalize_prompt(text),
    )
    embedding = response.data[0].embedding

    # Validate embedding dimension
    assert len(embedding) == settings.openai_embedding_dimension, (
        f"Embedding dimension mismatch: expected {settings.openai_embedding_dimension}, "
        f"got {len(embedding)}"
    )

    return embedding


async def check_cache(prompt: str, theme: str) -> Optional[dict]:
    """
    Check semantic cache. Two-stage:
    1. Exact SHA256 hash match (cheap — microseconds)
    2. Cosine similarity on embeddings (moderate — one embedding call)

    Returns cached deck JSON or None on miss.
    Non-fatal: any exception returns None (generation continues).
    """
    from services.db.session import get_raw_connection

    normalized = normalize_prompt(prompt + " " + theme)
    prompt_hash = hashlib.sha256(normalized.encode()).hexdigest()

    try:
        async with get_raw_connection() as conn:
            # Exact hash check
            exact = await conn.fetchrow(
                """
                SELECT result_json FROM prompt_cache
                WHERE prompt_hash = $1
                  AND expires_at > NOW()
                  AND invalidated_at IS NULL
                LIMIT 1
                """,
                prompt_hash,
            )

            if exact:
                await conn.execute(
                    "UPDATE prompt_cache SET hit_count = hit_count + 1 WHERE prompt_hash = $1",
                    prompt_hash,
                )
                logger.info("cache_exact_hit", prompt_hash=prompt_hash[:8])
                return json.loads(exact["result_json"])

            # Semantic similarity check
            embedding = await get_embedding(prompt)

            rows = await conn.fetch(
                """
                SELECT prompt_hash, prompt_embedding, result_json
                FROM prompt_cache
                WHERE expires_at > NOW() AND invalidated_at IS NULL
                ORDER BY created_at DESC
                LIMIT 500
                """
            )

            best_score = 0.0
            best_row = None

            for row in rows:
                score = cosine_similarity(embedding, list(row["prompt_embedding"]))
                if score > best_score:
                    best_score = score
                    best_row = row

            if best_score >= settings.cache_similarity_threshold and best_row:
                await conn.execute(
                    "UPDATE prompt_cache SET hit_count = hit_count + 1 WHERE prompt_hash = $1",
                    best_row["prompt_hash"],
                )
                logger.info("cache_semantic_hit", score=round(best_score, 4))
                return json.loads(best_row["result_json"])

            logger.info("cache_miss", best_score=round(best_score, 4))
            return None

    except Exception as e:
        logger.warning("cache_read_failed", error=str(e))
        return None


async def store_cache(prompt: str, theme: str, deck: dict) -> None:
    """Store a completed deck in the semantic cache. Non-fatal on failure."""
    from services.db.session import get_raw_connection

    normalized = normalize_prompt(prompt + " " + theme)
    prompt_hash = hashlib.sha256(normalized.encode()).hexdigest()

    try:
        embedding = await get_embedding(prompt)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.cache_ttl_hours)

        # Remove internal cost metadata before caching
        deck_to_cache = {k: v for k, v in deck.items() if not k.startswith("_")}

        async with get_raw_connection() as conn:
            await conn.execute(
                """
                INSERT INTO prompt_cache (prompt_hash, prompt_embedding, result_json, expires_at)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (prompt_hash) DO UPDATE
                SET result_json = EXCLUDED.result_json, expires_at = EXCLUDED.expires_at
                """,
                prompt_hash,
                embedding,
                json.dumps(deck_to_cache),
                expires_at,
            )
        logger.info("cache_stored", prompt_hash=prompt_hash[:8])

    except Exception as e:
        logger.warning("cache_write_failed", error=str(e))


async def invalidate_cache(pattern: str = "") -> int:
    """
    Manually invalidate cache entries matching a pattern.
    Sets invalidated_at rather than deleting — preserves audit trail.
    Called by admin DELETE /api/v1/cache endpoint.
    """
    from services.db.session import get_raw_connection

    try:
        async with get_raw_connection() as conn:
            if pattern:
                result = await conn.execute(
                    """
                    UPDATE prompt_cache SET invalidated_at = NOW()
                    WHERE prompt_hash LIKE $1 AND invalidated_at IS NULL
                    """,
                    f"%{pattern}%",
                )
            else:
                result = await conn.execute(
                    "UPDATE prompt_cache SET invalidated_at = NOW() WHERE invalidated_at IS NULL"
                )
            # asyncpg returns "UPDATE N" — extract count
            return int(result.split()[-1])
    except Exception as e:
        logger.error("cache_invalidation_failed", error=str(e))
        return 0


async def check_redis() -> str:
    """Health check for Redis connectivity."""
    import redis.asyncio as aioredis
    try:
        r = aioredis.from_url(settings.redis_url)
        await r.ping()
        await r.aclose()
        return "ok"
    except Exception as e:
        return f"error: {str(e)[:100]}"
