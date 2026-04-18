"""
Configuration for the ingestion microservice.
All sensitive values (API keys) must come from environment variables.
Never hardcode secrets in code.
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ── Pinecone ──────────────────────────────────────────────────────────────
    pinecone_api_key:     str = ""
    pinecone_index_name:  str = "aippt-documents"
    pinecone_environment: str = "us-east-1-aws"
    pinecone_dimension:   int = 1536      # text-embedding-3-small output dimension

    # ── OpenAI ────────────────────────────────────────────────────────────────
    openai_api_key:        str = ""
    openai_embedding_model: str = "text-embedding-3-small"
    openai_vision_model:    str = "gpt-4o-2024-08-06"
    openai_metadata_model:  str = "gpt-4o-mini"

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url:         str = "redis://localhost:6379/1"

    # ── AWS / S3 ──────────────────────────────────────────────────────────────
    aws_access_key_id:     str = ""
    aws_secret_access_key: str = ""
    aws_region:            str = "us-east-1"
    s3_raw_documents_bucket: str = "aippt-raw-documents"
    s3_images_bucket:      str = "aippt-extracted-images"

    # ── File limits ───────────────────────────────────────────────────────────
    max_file_size_mb:          int   = 50
    max_pages_per_document:    int   = 500
    max_images_per_document:   int   = 200

    # ── Chunking ──────────────────────────────────────────────────────────────
    max_chunk_tokens:    int = 512
    chunk_overlap_tokens: int = 64
    min_chunk_tokens:    int = 50

    # ── Retrieval ─────────────────────────────────────────────────────────────
    retrieval_top_k_initial: int   = 20    # Candidates before reranking
    retrieval_top_k_final:   int   = 8     # Passed to LLM context
    min_relevance_score:     float = 0.65  # Cosine similarity floor
    reranker_model:          str   = "BAAI/bge-reranker-large"

    # ── Vision ────────────────────────────────────────────────────────────────
    vision_concurrent_calls: int = 5    # Semaphore limit
    vision_max_retries:      int = 3

    # ── PII ───────────────────────────────────────────────────────────────────
    pii_redaction_enabled:  bool = True
    pii_reversible_tokens:  bool = True   # Unique tokens per entity (reversible)

    # ── Environment ───────────────────────────────────────────────────────────
    environment: str = "development"
    log_level:   str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()
