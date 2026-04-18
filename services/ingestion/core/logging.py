"""Structured logging configuration for the ingestion service."""
import logging
import structlog
from core.config import get_settings

settings = get_settings()


def setup_logging() -> None:
    """Configure structlog with JSON output for production."""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(format="%(message)s", level=level)


def get_logger(name: str = "ingestion"):
    return structlog.get_logger(name).bind(
        service="ingestion",
        env=settings.environment,
    )
