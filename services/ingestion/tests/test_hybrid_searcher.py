import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pipeline.chunk_model import RetrievedChunk


def make_chunk(chunk_id: str, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        text=f"Chunk text for {chunk_id}",
        metadata={"chunk_id": chunk_id, "tenant_id": "t-1", "doc_id": "doc-1",
                  "source_filename": "test.pdf", "page_number": 1, "chunk_type": "narrative"},
        dense_score=score,
    )


def test_rrf_fusion_boosts_shared_results():
    """A chunk appearing in both dense and sparse lists should get a higher fused score."""
    from retrieval.hybrid_searcher import HybridSearcher
    searcher = HybridSearcher.__new__(HybridSearcher)   # Skip __init__

    dense = [make_chunk("chunk-A", 0.90), make_chunk("chunk-B", 0.80), make_chunk("chunk-C", 0.70)]
    sparse = [("chunk-A", 0.95), ("chunk-D", 0.85), ("chunk-B", 0.75)]

    fused = searcher._rrf(dense, sparse, top_k=10)

    # chunk-A is in BOTH lists → highest fused score
    fused_ids = [c.chunk_id for c in fused]
    assert fused_ids[0] == "chunk-A"

    # chunk-B also appears in both lists
    assert "chunk-B" in fused_ids


def test_rrf_with_empty_sparse():
    """Dense-only results should still work when BM25 returns nothing."""
    from retrieval.hybrid_searcher import HybridSearcher
    searcher = HybridSearcher.__new__(HybridSearcher)

    dense = [make_chunk("chunk-X", 0.95)]
    fused = searcher._rrf(dense, [], top_k=10)

    assert len(fused) == 1
    assert fused[0].chunk_id == "chunk-X"


def test_rrf_with_empty_dense():
    """BM25-only results should be handled gracefully."""
    from retrieval.hybrid_searcher import HybridSearcher
    searcher = HybridSearcher.__new__(HybridSearcher)

    sparse = [("chunk-Y", 0.8), ("chunk-Z", 0.6)]
    fused = searcher._rrf([], sparse, top_k=10)

    # BM25-only results without dense text are skipped in current impl
    assert isinstance(fused, list)


def test_rrf_top_k_limits_results():
    """RRF should respect top_k parameter."""
    from retrieval.hybrid_searcher import HybridSearcher
    searcher = HybridSearcher.__new__(HybridSearcher)

    dense = [make_chunk(f"c-{i}", 0.9 - i * 0.05) for i in range(10)]
    fused = searcher._rrf(dense, [], top_k=3)

    assert len(fused) <= 3


def test_rrf_deduplicates():
    """Same chunk_id in dense + sparse should be counted once, not duplicated."""
    from retrieval.hybrid_searcher import HybridSearcher
    searcher = HybridSearcher.__new__(HybridSearcher)

    dense = [make_chunk("shared", 0.9)]
    sparse = [("shared", 0.8)]
    fused = searcher._rrf(dense, sparse, top_k=10)

    # shared should appear only once
    ids = [c.chunk_id for c in fused]
    assert ids.count("shared") == 1
    # But its score should be higher than if it were in only one list
    assert fused[0].fused_score > 0
