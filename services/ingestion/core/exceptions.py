"""Custom exceptions for the ingestion pipeline."""


class DocumentTooLargeError(Exception):
    """File exceeds max_file_size_mb OR max_pages_per_document."""
    def __init__(self, actual: float, limit: float, unit: str = "MB"):
        self.actual = actual
        self.limit  = limit
        super().__init__(f"Document too large: {actual:.1f} {unit} (limit: {limit} {unit})")


class UnsupportedFileTypeError(Exception):
    """MIME type not supported by the ingestion pipeline."""
    def __init__(self, mime_type: str):
        self.mime_type = mime_type
        super().__init__(f"Unsupported file type: {mime_type}")


class ParseFailedError(Exception):
    """Document parser returned 0 elements or threw an unrecoverable error."""
    def __init__(self, doc_id: str, reason: str):
        self.doc_id = doc_id
        self.reason = reason
        super().__init__(f"Parse failed ({doc_id[:8]}…): {reason}")


class DuplicateDocumentError(Exception):
    """This exact document content has already been ingested for this tenant."""
    def __init__(self, doc_hash: str, existing_doc_id: str):
        self.doc_hash        = doc_hash
        self.existing_doc_id = existing_doc_id
        super().__init__(
            f"Duplicate document detected (hash: {doc_hash[:16]}…). "
            f"Already indexed as: {existing_doc_id}"
        )


class EmbeddingFailedError(Exception):
    """OpenAI embedding API failed after all retries."""
    pass


class IndexingFailedError(Exception):
    """Pinecone upsert failed after all retries."""
    pass


class RetrievalError(Exception):
    """Hybrid search or reranking failed unrecoverably."""
    pass
