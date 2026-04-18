from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # AWS / S3
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"
    s3_bucket: str = "aippt-exports"

    # Pre-signed URL expiry per plan tier (seconds)
    url_expiry_free: int       = 3_600       # 1 hour
    url_expiry_pro: int        = 86_400      # 24 hours
    url_expiry_enterprise: int = 604_800     # 7 days

    # Service URLs
    main_api_url: str = "http://localhost:8000"

    # Font storage
    font_dir: str = "/app/fonts"

    # Limits
    max_pptx_size_mb: int    = 100
    max_image_size_mb: int   = 20
    max_slides_per_deck: int = 100

    # Environment
    environment: str = "development"
    log_level: str   = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()
