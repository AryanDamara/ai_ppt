"""
Tests for the layout parser module.

These tests verify the parser's element type detection, section path tracking,
and fallback behaviour. Since Docling requires model downloads, we test
the internal conversion logic with mocked Docling objects.
"""
import pytest
from unittest.mock import MagicMock, patch
from pipeline.parsers.layout_parser import LayoutParser, ParsedElement, ElementType


def test_parsed_element_creation():
    """ParsedElement should store all required attributes."""
    elem = ParsedElement(
        element_type=ElementType.PARAGRAPH,
        text="Revenue grew 34% YoY.",
        page_number=5,
    )
    assert elem.element_type == ElementType.PARAGRAPH
    assert elem.text == "Revenue grew 34% YoY."
    assert elem.page_number == 5
    assert elem.heading_level == 0
    assert elem.section_path == []


def test_heading_element_stores_level():
    """Heading elements should store their heading level."""
    elem = ParsedElement(
        element_type=ElementType.HEADING,
        text="Executive Summary",
        page_number=1,
        heading_level=1,
    )
    assert elem.heading_level == 1


def test_figure_element_stores_image_bytes():
    """Figure elements should store image bytes and caption."""
    img_bytes = b"\x89PNG" + b"\x00" * 100
    elem = ParsedElement(
        element_type=ElementType.FIGURE,
        text="",
        page_number=3,
        image_bytes=img_bytes,
        image_caption="Figure 1: Revenue trend",
    )
    assert elem.image_bytes == img_bytes
    assert elem.image_caption == "Figure 1: Revenue trend"


def test_table_element_stores_data():
    """Table elements should store structured table data."""
    table_data = {"headers": ["Q", "Rev"], "rows": [{"Q": "Q1", "Rev": "$5M"}]}
    elem = ParsedElement(
        element_type=ElementType.TABLE,
        text="| Q | Rev |\n|---|---|\n| Q1 | $5M |",
        page_number=2,
    )
    elem.table_data = table_data
    assert elem.table_data is not None
    assert elem.table_data["headers"] == ["Q", "Rev"]


def test_mime_to_suffix_mapping():
    """MIME type to file suffix mapping should cover all supported types."""
    assert LayoutParser._mime_to_suffix("application/pdf") == ".pdf"
    assert LayoutParser._mime_to_suffix("application/vnd.openxmlformats-officedocument.wordprocessingml.document") == ".docx"
    assert LayoutParser._mime_to_suffix("text/plain") == ".txt"
    assert LayoutParser._mime_to_suffix("text/csv") == ".csv"
    assert LayoutParser._mime_to_suffix("application/unknown") == ".bin"


def test_element_type_enum_values():
    """Verify all element types have expected string values."""
    assert ElementType.HEADING.value == "heading"
    assert ElementType.PARAGRAPH.value == "paragraph"
    assert ElementType.TABLE.value == "table"
    assert ElementType.FIGURE.value == "figure"
    assert ElementType.LIST_ITEM.value == "list_item"
    assert ElementType.CAPTION.value == "caption"
    assert ElementType.FOOTNOTE.value == "footnote"
    assert ElementType.PAGE_HEADER.value == "page_header"
    assert ElementType.PAGE_FOOTER.value == "page_footer"


def test_fallback_extraction_parses_markdown():
    """Fallback extraction should create elements from markdown headings and paragraphs."""
    # Create a real parser instance would require Docling, so we test the fallback method
    with patch.object(LayoutParser, "__init__", lambda x: None):
        parser = LayoutParser()
        parser._converter = None

        # Simulate a Docling document that exports to markdown
        mock_doc = MagicMock()
        mock_doc.export_to_markdown.return_value = """# Introduction

This is the first paragraph of the introduction.

## Revenue Analysis

Revenue grew 34% year-over-year.

- Q1: $4.2M
- Q2: $5.1M

| Quarter | Revenue |
|---------|---------|
| Q1      | $4.2M   |
"""
        elements = parser._fallback_extraction(mock_doc)
        assert len(elements) > 0

        types = [e.element_type for e in elements]
        assert ElementType.HEADING in types
        assert ElementType.PARAGRAPH in types
        assert ElementType.LIST_ITEM in types
        assert ElementType.TABLE in types

        # Check heading levels
        headings = [e for e in elements if e.element_type == ElementType.HEADING]
        assert any(h.heading_level == 1 for h in headings)
        assert any(h.heading_level == 2 for h in headings)
