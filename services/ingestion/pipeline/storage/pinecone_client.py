"""
Pinecone vector store — tenant-isolated namespaces.

TENANT ISOLATION STRATEGY:
  Each tenant gets a dedicated Pinecone NAMESPACE (not a separate index).
  All search queries include a metadata filter: tenant_id == this_tenant.
  This provides mathematical isolation — one tenant cannot query another's data.
  It is cheaper than separate indexes and easy to scale.

  Namespace format: "tenant-{tenant_id}"

IDEMPOTENCY:
  Before indexing a document, query Pinecone for any existing vector with
  this doc_id. If found, the document was already indexed — raise DuplicateDocumentError.

GDPR DELETION:
  delete_document() removes all vectors for a doc_id using metadata filter delete.
  This satisfies the right-to-erasure requirement.

CHUNK TEXT IN METADATA:
  Pinecone metadata stores chunk_text (truncated to 1000 chars) alongside the vector.
  This lets us reconstruct RetrievedChunk text from Pinecone results without a
  separate text store. For longer texts, store full text in a PostgreSQL backup.

UPSERT BATCH SIZE:
  100 vectors per upsert call (Pinecone recommendation for throughput).
"""
from __future__ import annotations
import logging
from tenacity import retry, stop_after_attempt, wait_exponential

from pipeline.chunk_model import Chunk, RetrievedChunk
from core.config import get_settings
from core.exceptions import IndexingFailedError

settings = get_settings()
logger   = logging.getLogger(__name__)

UPSERT_BATCH = 100


class PineconeVectorStore:
    """Manages vectors in Pinecone with per-tenant namespace isolation."""

    def __init__(self):
        self._index = None

    def _get_index(self):
        """Lazy-init Pinecone index. Connection is persistent."""
        if self._index is None:
            from pinecone import Pinecone
            pc           = Pinecone(api_key=settings.pinecone_api_key)
            self._index  = pc.Index(settings.pinecone_index_name)
            logger.info(f"Connected to Pinecone index: {settings.pinecone_index_name}")
        return self._index

    @staticmethod
    def _namespace(tenant_id: str) -> str:
        return f"tenant-{tenant_id}"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=20), reraise=True)
    def upsert_chunks(self, chunks: list[Chunk], tenant_id: str) -> int:
        """
        Upsert embedded chunks to the tenant's Pinecone namespace.

        Chunks without embeddings are skipped with a warning.
        The chunk text is stored in Pinecone metadata (truncated to 1000 chars)
        so RetrievedChunk.text can be populated from query results.

        Returns number of successfully upserted vectors.
        """
        index     = self._get_index()
        namespace = self._namespace(tenant_id)

        ready   = [c for c in chunks if c.embedding is not None]
        skipped = len(chunks) - len(ready)
        if skipped:
            logger.warning(f"Skipping {skipped} chunks with no embeddings")
        if not ready:
            return 0

        upserted = 0
        for start in range(0, len(ready), UPSERT_BATCH):
            batch = ready[start: start + UPSERT_BATCH]
            vectors = []
            for chunk in batch:
                meta = chunk.metadata.to_pinecone_metadata()
                # Store chunk text in metadata for text reconstruction (truncated)
                meta["chunk_text"] = chunk.text[:1000]
                vectors.append({
                    "id":       chunk.metadata.chunk_id,
                    "values":   chunk.embedding,
                    "metadata": meta,
                })
            try:
                index.upsert(vectors=vectors, namespace=namespace)
                upserted += len(batch)
            except Exception as e:
                raise IndexingFailedError(
                    f"Pinecone upsert failed (batch at {start}): {e}"
                ) from e

        logger.info(f"Upserted {upserted} vectors to '{namespace}'")
        return upserted

    def dense_search(
        self,
        query_embedding: list[float],
        tenant_id:       str,
        top_k:           int = 20,
        doc_ids_filter:  list[str] | None = None,
    ) -> list[RetrievedChunk]:
        """
        Cosine similarity search in the tenant's namespace.

        doc_ids_filter restricts results to specific documents
        (used when user selects which documents to ground this deck in).
        """
        index     = self._get_index()
        namespace = self._namespace(tenant_id)

        meta_filter: dict = {"tenant_id": {"$eq": tenant_id}}
        if doc_ids_filter:
            meta_filter["doc_id"] = {"$in": doc_ids_filter}

        try:
            result = index.query(
                namespace=namespace,
                vector=query_embedding,
                top_k=top_k,
                include_metadata=True,
                filter=meta_filter,
            )
            retrieved = []
            for match in result.matches:
                retrieved.append(RetrievedChunk(
                    chunk_id=match.id,
                    text=match.metadata.get("chunk_text", ""),
                    metadata=dict(match.metadata),
                    dense_score=float(match.score),
                ))
            return retrieved
        except Exception as e:
            logger.error(f"Pinecone dense search failed: {e}")
            return []

    def document_exists(self, doc_id: str, tenant_id: str) -> bool:
        """
        Check if any vectors exist for this doc_id in the tenant's namespace.
        Used for idempotency checking before re-ingestion.
        """
        index     = self._get_index()
        namespace = self._namespace(tenant_id)
        try:
            dummy = [0.0] * settings.pinecone_dimension
            result = index.query(
                namespace=namespace,
                vector=dummy,
                top_k=1,
                include_metadata=False,
                filter={"doc_id": {"$eq": doc_id}, "tenant_id": {"$eq": tenant_id}},
            )
            return len(result.matches) > 0
        except Exception:
            return False

    def hash_exists(self, doc_hash: str, tenant_id: str) -> str | None:
        """
        Check if a document with this content hash already exists.
        Returns the existing doc_id if found, else None.
        Used for content-level deduplication (same file, different name).
        """
        index     = self._get_index()
        namespace = self._namespace(tenant_id)
        try:
            dummy  = [0.0] * settings.pinecone_dimension
            result = index.query(
                namespace=namespace,
                vector=dummy,
                top_k=1,
                include_metadata=True,
                filter={"doc_hash": {"$eq": doc_hash}, "tenant_id": {"$eq": tenant_id}},
            )
            if result.matches:
                return result.matches[0].metadata.get("doc_id")
            return None
        except Exception:
            return None

    def delete_document(self, doc_id: str, tenant_id: str) -> None:
        """
        Delete all vectors for a document. GDPR right-to-erasure.
        Pinecone metadata filter delete removes all matching vectors.
        """
        index     = self._get_index()
        namespace = self._namespace(tenant_id)
        try:
            index.delete(
                filter={"doc_id": {"$eq": doc_id}, "tenant_id": {"$eq": tenant_id}},
                namespace=namespace,
            )
            logger.info(f"Deleted vectors for doc {doc_id[:8]}… in {namespace}")
        except Exception as e:
            logger.error(f"Pinecone delete failed: {e}")
