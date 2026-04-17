class PipelineError(Exception):
    """Raised when the AI generation pipeline fails at any step."""
    def __init__(self, message: str, step: int, retryable: bool = True):
        self.message = message
        self.step = step
        self.retryable = retryable
        super().__init__(message)

class SchemaValidationError(Exception):
    """Raised when AI output fails JSON schema validation."""
    def __init__(self, errors: list[str], step: int):
        self.errors = errors
        self.step = step
        super().__init__(f"Schema validation failed at step {step}: {errors}")

class ContentSizeError(Exception):
    """Raised when generated slide content exceeds size limits."""
    def __init__(self, actual_bytes: int, limit_bytes: int, slide_type: str):
        self.actual_bytes = actual_bytes
        self.limit_bytes = limit_bytes
        self.slide_type = slide_type
        super().__init__(
            f"Content for {slide_type} is {actual_bytes}B, exceeds {limit_bytes}B limit"
        )

class ModelMismatchError(Exception):
    """Raised when OpenAI routes to a different model than requested."""
    def __init__(self, requested: str, actual: str):
        self.requested = requested
        self.actual = actual
        super().__init__(f"Model mismatch: requested {requested}, got {actual}")

class CacheError(Exception):
    """Non-fatal: cache read/write failed."""
    pass

class JobNotFoundError(Exception):
    """job_id does not exist in Redis."""
    pass

class RateLimitError(Exception):
    """Client exceeded generation rate limit."""
    pass

class IdempotencyError(Exception):
    """Duplicate client_request_id detected — return existing job."""
    def __init__(self, job_id: str, status: str):
        self.job_id = job_id
        self.status = status
        super().__init__(f"Duplicate request — existing job: {job_id}")
