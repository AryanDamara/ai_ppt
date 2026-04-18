import pytest
from pipeline.chunk_model import RetrievedChunk
from retrieval.context_packer import ContextPacker


def _make_chunk(
    chunk_id: str,
    text: str,
    rerank_score: float = 0.9,
    page_number: int = 1,
    source_filename: str = "report.pdf",
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        text=text,
        metadata={
            "chunk_id": chunk_id,
            "doc_id": "doc-1",
            "tenant_id": "t-1",
            "source_filename": source_filename,
            "page_number": page_number,
            "chunk_type": "narrative",
        },
        rerank_score=rerank_score,
    )


def test_empty_chunks_returns_empty_context():
    packer = ContextPacker()
    result = packer.pack([], query="test")
    assert result["context_string"] == ""
    assert result["citation_map"] == {}
    assert result["total_tokens"] == 0


def test_chunks_are_labelled_as_sources():
    packer = ContextPacker()
    chunks = [
        _make_chunk("c-1", "First chunk of relevant text about revenue."),
        _make_chunk("c-2", "Second chunk about growth metrics."),
    ]
    result = packer.pack(chunks, query="revenue")
    assert "[Source 1]" in result["context_string"]
    assert "[Source 2]" in result["context_string"]
    assert "Source 1" in result["citation_map"]
    assert "Source 2" in result["citation_map"]


def test_deduplication_by_chunk_id():
    """Same chunk_id should appear only once in context."""
    packer = ContextPacker()
    chunks = [
        _make_chunk("c-1", "Duplicate chunk text."),
        _make_chunk("c-1", "Duplicate chunk text."),   # Same ID
        _make_chunk("c-2", "Different chunk text."),
    ]
    result = packer.pack(chunks, query="test")
    assert result["chunks_included"] == 2   # Deduped: only 2 unique


def test_token_budget_respected():
    """Packer should not exceed max_tokens budget."""
    packer = ContextPacker()
    # Create chunks with lots of text
    chunks = [
        _make_chunk(f"c-{i}", "Very long text. " * 200, rerank_score=0.9 - i * 0.01)
        for i in range(20)
    ]
    result = packer.pack(chunks, query="test", max_tokens=500)
    assert result["total_tokens"] <= 500
    assert result["chunks_excluded"] > 0


def test_citation_list_matches_citation_map():
    packer = ContextPacker()
    chunks = [
        _make_chunk("c-1", "Revenue data.", rerank_score=0.95, page_number=12),
        _make_chunk("c-2", "Growth metrics.", rerank_score=0.85, page_number=15),
    ]
    result = packer.pack(chunks, query="revenue")
    citations = packer.build_citation_list(result["citation_map"])

    assert len(citations) == 2
    assert citations[0]["chunk_id"] == "c-1"
    assert citations[0]["page_number"] == 12
    assert citations[1]["chunk_id"] == "c-2"
    assert 0 <= citations[0]["confidence_score"] <= 1.0


def test_source_metadata_in_context_string():
    packer = ContextPacker()
    chunks = [
        _make_chunk("c-1", "Important finding.", page_number=42, source_filename="annual_report.pdf"),
    ]
    result = packer.pack(chunks, query="findings")
    assert "annual_report.pdf" in result["context_string"]
    assert "p.42" in result["context_string"]
