from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # Database — with connection pooling config
    database_url: str = "postgresql+asyncpg://aippt:aipptdev@localhost:5432/aippt"
    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_pool_timeout: int = 30

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # OpenAI — pinned versions
    openai_api_key: str
    openai_model_primary: str = "gpt-4o-2024-08-06"
    openai_model_fast: str = "gpt-4o-mini"
    openai_model_fallback: str = "gpt-4o-mini"   # Fallback if primary fails
    openai_embedding_model: str = "text-embedding-3-small"
    openai_timeout_seconds: int = 30              # Hard timeout per API call
    openai_embedding_dimension: int = 1536        # text-embedding-3-small dimension

    # Pipeline
    pipeline_version: str = "1.0.0"
    schema_version: str = "1.0.0"
    max_slide_content_bytes: int = 50_000         # 50KB per slide
    slide_generation_timeout_seconds: int = 15    # Per-slide timeout

    # Rate limiting
    rate_limit_per_minute: int = 10               # Per IP

    # Semantic cache
    cache_similarity_threshold: float = 0.92
    cache_ttl_hours: int = 24

    # Environment
    environment: str = "development"
    log_level: str = "INFO"

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings() -> Settings:
    return Settings()
