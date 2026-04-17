import re
import hashlib
from typing import Optional

# Prompt injection patterns — block attempts to override system instructions
INJECTION_PATTERNS = [
    re.compile(r'(?i)ignore\s+(all\s+)?(previous|earlier)\s+(instructions?|commands?|prompts?)'),
    re.compile(r'(?i)system\s*:\s*you\s+are\s+now'),
    re.compile(r'(?i)\[\s*system\s*\]'),
    re.compile(r'(?i)<\s*/?\s*system\s*>'),
    re.compile(r'(?i)act\s+as\s+if\s+you\s+(are|were)\s+(not\s+an?\s+ai|a\s+human|unrestricted)'),
    re.compile(r'(?i)pretend\s+(you\s+are|to\s+be)\s+(not\s+an?\s+ai|a\s+human|unrestricted)'),
    re.compile(r'(?i)disregard\s+(your|all\s+previous)\s+(training|instructions?)'),
    re.compile(r'(?i)jailbreak'),
    re.compile(r'(?i)DAN\s+mode'),
]


def sanitize_prompt(prompt: str) -> str:
    """
    Sanitize user prompt before passing to AI pipeline.
    - Removes prompt injection attempts
    - Normalizes whitespace
    - Enforces length limit

    Returns the cleaned prompt string.
    """
    cleaned = prompt.strip()

    for pattern in INJECTION_PATTERNS:
        cleaned = pattern.sub('[INPUT_SANITIZED]', cleaned)

    # Normalize excessive whitespace
    cleaned = re.sub(r'\s{3,}', ' ', cleaned)

    # Hard length cap (Pydantic already validates, this is a second layer)
    cleaned = cleaned[:2000]

    return cleaned


def compute_client_fingerprint(client_request_id: Optional[str], prompt: str, theme: str) -> str:
    """
    Compute idempotency key from client_request_id if provided,
    or from prompt + theme hash as fallback.
    Used to detect and deduplicate rapid duplicate submissions.
    """
    if client_request_id:
        return hashlib.sha256(client_request_id.encode()).hexdigest()[:32]

    combined = f"{prompt.strip().lower()}::{theme}"
    return hashlib.sha256(combined.encode()).hexdigest()[:32]
