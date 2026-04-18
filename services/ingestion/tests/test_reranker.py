import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pipeline.chunk_model import RetrievedChunk


def _make_chunk(chunk_id: str, text: str, dense_score: float = 0.8) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        text=text,
        metadata={"chunk_id": chunk_id, "doc_id": "doc-1", "tenant_id": "t-1",
                  "source_filename": "test.pdf", "page_number": 1, "chunk_type": "narrative"},
        dense_score=dense_score,
        fused_score=dense_score,
    )


@pytest.mark.asyncio
async def test_reranker_fallback_on_unavailable_model():
    """When model fails to load, reranker should fall back to fused_score ordering."""
    from retrieval.reranker import CrossEncoderReranker

    # Patch _load_model to return None (model unavailable)
    with patch("retrieval.reranker._load_model", return_value=None):
        reranker = CrossEncoderReranker()

        chunks = [
            _make_chunk("c-1", "Low relevance text", dense_score=0.5),
            _make_chunk("c-2", "High relevance text", dense_score=0.9),
            _make_chunk("c-3", "Medium relevance text", dense_score=0.7),
        ]
        # Set fused scores to match dense_score for this test
        for c in chunks:
            c.fused_score = c.dense_score

        result = await reranker.rerank("test query", chunks, top_k=2)

        # Should return top 2 by fused_score
        assert len(result) == 2
        assert result[0].chunk_id == "c-2"  # Highest fused score
        assert result[1].chunk_id == "c-3"


@pytest.mark.asyncio
async def test_reranker_empty_chunks():
    """Reranker should return empty list for empty input."""
    from retrieval.reranker import CrossEncoderReranker

    reranker = CrossEncoderReranker()
    result = await reranker.rerank("test query", [], top_k=5)
    assert result == []


@pytest.mark.asyncio
async def test_reranker_respects_top_k():
    """Reranker should return at most top_k results."""
    from retrieval.reranker import CrossEncoderReranker

    with patch("retrieval.reranker._load_model", return_value=None):
        reranker = CrossEncoderReranker()

        chunks = [_make_chunk(f"c-{i}", f"Text {i}", 0.8 - i * 0.05) for i in range(10)]
        for c in chunks:
            c.fused_score = c.dense_score

        result = await reranker.rerank("query", chunks, top_k=3)
        assert len(result) <= 3
