import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_chunk(text: str, chunk_id: str = "doc-test_c0001"):
    """Create a test Chunk without embedding."""
    from pipeline.chunk_model import Chunk, ChunkMetadata, ChunkType
    return Chunk(
        text=text,
        metadata=ChunkMetadata(
            chunk_id=chunk_id,
            doc_id="doc-test",
            doc_hash="a" * 64,
            tenant_id="t-1",
            page_number=1,
            section=None,
            headers_path="",
            source_filename="test.pdf",
            source_uri="",
            chunk_type=ChunkType.NARRATIVE_TEXT,
        ),
    )


@pytest.mark.asyncio
async def test_embed_chunks_populates_embeddings():
    """embed_chunks should populate chunk.embedding for all chunks."""
    from pipeline.embedders.batch_embedder import BatchEmbedder

    chunks = [_make_chunk(f"Text for chunk {i}", f"doc-test_c{i:04d}") for i in range(3)]

    fake_embedding = [0.1] * 1536

    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=fake_embedding) for _ in range(3)]

    with patch.object(BatchEmbedder, "__init__", lambda x: None):
        embedder = BatchEmbedder()
        embedder._client = MagicMock()
        embedder._client.embeddings = MagicMock()
        embedder._client.embeddings.create = AsyncMock(return_value=mock_response)

        result = await embedder.embed_chunks(chunks)

        assert len(result) == 3
        for chunk in result:
            assert chunk.embedding is not None
            assert len(chunk.embedding) == 1536


@pytest.mark.asyncio
async def test_embed_chunks_empty_list():
    """embed_chunks should return empty list for empty input."""
    from pipeline.embedders.batch_embedder import BatchEmbedder

    with patch.object(BatchEmbedder, "__init__", lambda x: None):
        embedder = BatchEmbedder()
        result = await embedder.embed_chunks([])
        assert result == []


@pytest.mark.asyncio
async def test_dimension_mismatch_raises():
    """Wrong embedding dimension should raise EmbeddingFailedError."""
    from pipeline.embedders.batch_embedder import BatchEmbedder
    from core.exceptions import EmbeddingFailedError

    chunks = [_make_chunk("Test text")]

    wrong_dim_embedding = [0.1] * 768   # Wrong dimension (should be 1536)

    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=wrong_dim_embedding)]

    with patch.object(BatchEmbedder, "__init__", lambda x: None):
        embedder = BatchEmbedder()
        embedder._client = MagicMock()
        embedder._client.embeddings = MagicMock()
        embedder._client.embeddings.create = AsyncMock(return_value=mock_response)

        with pytest.raises(EmbeddingFailedError, match="dimension mismatch"):
            await embedder.embed_chunks(chunks)
