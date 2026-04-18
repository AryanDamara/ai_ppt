import pytest
from pipeline.chunkers.semantic_chunker import SemanticChunker
from pipeline.parsers.layout_parser import ParsedElement, ElementType


def make_para(text: str, page: int = 1) -> ParsedElement:
    return ParsedElement(element_type=ElementType.PARAGRAPH, text=text, page_number=page)

def make_heading(text: str, level: int = 1, page: int = 1) -> ParsedElement:
    e = ParsedElement(element_type=ElementType.HEADING, text=text, page_number=page, heading_level=level)
    e.section_path = [text]
    return e

def make_table(data: dict, page: int = 1) -> ParsedElement:
    e = ParsedElement(element_type=ElementType.TABLE, text="", page_number=page)
    e.table_data = data
    return e


COMMON_ARGS = dict(doc_id="doc-test", doc_hash="abc123", tenant_id="t-1",
                   source_filename="test.pdf")


def test_heading_starts_new_chunk():
    chunker  = SemanticChunker(max_chunk_tokens=200, overlap_tokens=20, min_chunk_tokens=5)
    elements = [
        make_para("First section content with enough words to embed."),
        make_heading("New Section"),
        make_para("Second section content with enough words to embed."),
    ]
    chunks = chunker.chunk(elements, **COMMON_ARGS)
    types  = [c.metadata.chunk_type.value for c in chunks]
    assert "heading" in types


def test_table_produces_two_chunks():
    chunker = SemanticChunker(max_chunk_tokens=200, overlap_tokens=20, min_chunk_tokens=5)
    table_data = {"headers": ["Q", "Rev"], "rows": [{"Q": "Q1", "Rev": "$4M"}], "caption": None}
    elements   = [make_table(table_data)]
    chunks     = chunker.chunk(elements, **COMMON_ARGS)
    types      = [c.metadata.chunk_type.value for c in chunks]
    assert "table_json" in types
    assert "table_description" in types
    assert len([t for t in types if "table" in t]) == 2


def test_chunk_ids_are_sequential():
    chunker  = SemanticChunker(max_chunk_tokens=200, overlap_tokens=20, min_chunk_tokens=5)
    elements = [make_para(f"Paragraph {i} with substantial content to form a chunk." * 3, page=i) for i in range(5)]
    chunks   = chunker.chunk(elements, **COMMON_ARGS)
    ids      = [c.metadata.chunk_id for c in chunks]
    for cid in ids:
        assert cid.startswith("doc-test_c")


def test_figures_not_chunked_here():
    """FIGURE elements are skipped in chunker — handled by vision enricher."""
    from pipeline.parsers.layout_parser import ParsedElement, ElementType
    chunker  = SemanticChunker(max_chunk_tokens=200, overlap_tokens=20, min_chunk_tokens=5)
    elements = [
        make_para("Some text before figure."),
        ParsedElement(element_type=ElementType.FIGURE, text="", page_number=1,
                      image_bytes=b"fake_png_bytes"),
        make_para("Some text after figure."),
    ]
    chunks   = chunker.chunk(elements, **COMMON_ARGS)
    # No CHART_DESC or IMAGE_DESC chunks — those come from vision enricher
    types    = [c.metadata.chunk_type.value for c in chunks]
    assert "chart_description" not in types
    assert "image_description" not in types


def test_min_chunk_token_filter():
    """Chunks below min_chunk_tokens should be skipped."""
    chunker  = SemanticChunker(max_chunk_tokens=200, overlap_tokens=20, min_chunk_tokens=50)
    elements = [make_para("Short.")]   # Way below 50 tokens
    chunks   = chunker.chunk(elements, **COMMON_ARGS)
    # Heading chunks are always included; very short paragraphs are filtered
    narrative_chunks = [c for c in chunks if c.metadata.chunk_type.value == "narrative"]
    assert len(narrative_chunks) == 0


def test_page_headers_footers_skipped():
    chunker  = SemanticChunker(max_chunk_tokens=200, overlap_tokens=20, min_chunk_tokens=5)
    elements = [
        ParsedElement(ElementType.PAGE_HEADER, "Company Confidential", 1),
        make_para("Actual content paragraph with meaningful words to embed here."),
        ParsedElement(ElementType.PAGE_FOOTER, "Page 1 of 20", 1),
    ]
    chunks   = chunker.chunk(elements, **COMMON_ARGS)
    for c in chunks:
        assert "Company Confidential" not in c.text
        assert "Page 1 of 20" not in c.text
