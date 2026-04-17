import structlog
import logging
from contextvars import ContextVar
from core.config import get_settings
import re

settings = get_settings()

# Thread-safe request ID context
request_id_var: ContextVar[str] = ContextVar('request_id', default='unknown')
job_id_var: ContextVar[str] = ContextVar('job_id', default='none')

# PII patterns to redact from logs
PII_PATTERNS = [
    (re.compile(r'\d{3}-\d{2}-\d{4}'), '[SSN_REDACTED]'),
    (re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'), '[EMAIL_REDACTED]'),
    (re.compile(r'\b(?:\d{4}[- ]?){3}\d{4}\b'), '[CARD_REDACTED]'),
    (re.compile(r'\b\d{10,}\b'), '[PHONE_REDACTED]'),
]

def redact_pii(text: str) -> str:
    """Remove PII patterns from text before logging."""
    for pattern, replacement in PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def setup_logging() -> None:
    """Configure structlog for structured JSON logging."""
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

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

    logging.basicConfig(
        format="%(message)s",
        level=log_level,
    )


def get_logger(name: str = "aippt"):
    """Get a context-bound logger with request_id and job_id injected."""
    return structlog.get_logger(name).bind(
        request_id=request_id_var.get(),
        job_id=job_id_var.get(),
        service="aippt-api",
        environment=settings.environment,
    )
