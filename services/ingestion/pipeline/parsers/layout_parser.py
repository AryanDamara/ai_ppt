"""
Docling layout-aware document parser.

WHY LAYOUT-AWARE:
  Standard PDF text extraction reads bytes in the order they appear in the PDF
  binary, which is NOT reading order. A three-column annual report gets text from
  all three columns interleaved. Docling uses a computer vision pipeline to detect
  bounding boxes, determine reading order within each column, and produce text
  that matches how a human would read the page.

Docling supports:
  PDF, DOCX, PPTX, XLSX, HTML, Markdown, Image files

Docling automatically handles:
  - Multi-column layouts (reads within each column)
  - Scanned pages (triggers OCR via Tesseract when no text layer detected)
  - Tables (detects table structure, exposes grid for extraction)
  - Figures (extracts image crops for vision enrichment)
  - Reading order (top-to-bottom within each detected region)

Output: list[ParsedElement] in document reading order.
Element types: HEADING, PARAGRAPH, TABLE, FIGURE, LIST_ITEM, CAPTION, FOOTNOTE
"""
from __future__ import annotations
import logging
import os
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class ElementType(str, Enum):
    HEADING      = "heading"
    PARAGRAPH    = "paragraph"
    TABLE        = "table"
    FIGURE       = "figure"
    LIST_ITEM    = "list_item"
    CAPTION      = "caption"
    FOOTNOTE     = "footnote"
    PAGE_HEADER  = "page_header"    # Repeated page headers — skip these
    PAGE_FOOTER  = "page_footer"    # Repeated page footers — skip these


@dataclass
class ParsedElement:
    """One structural unit extracted from a document."""
    element_type:  ElementType
    text:          str                    # Extracted text (empty for pure images)
    page_number:   int                    # 1-indexed
    heading_level: int = 0               # 1-6 for headings; 0 otherwise
    section_path:  list[str] = field(default_factory=list)  # ["Exec Summary", "Revenue"]
    table_data:    Optional[dict] = None  # Populated by table_extractor.py
    image_bytes:   Optional[bytes] = None # PNG bytes for figures (for vision enricher)
    image_caption: Optional[str] = None


class LayoutParser:
    """
    Docling-powered layout-aware parser.
    One instance is created at service startup and reused (model loading is expensive).
    """

    def __init__(self):
        self._converter = None
        self._init_docling()

    def _init_docling(self):
        """
        Initialise Docling converter with OCR, table structure, and image extraction.
        This triggers model downloads on first run (~2GB total for all models).
        Subsequent runs use cached models.
        """
        try:
            from docling.document_converter import DocumentConverter
            from docling.datamodel.pipeline_options import (
                PdfPipelineOptions, EasyOcrOptions,
            )

            pdf_opts = PdfPipelineOptions(
                do_ocr=True,
                do_table_structure=True,
                generate_page_images=True,
                generate_picture_images=True,
                images_scale=2.0,           # 2× for better vision model quality
                ocr_options=EasyOcrOptions(lang=["en", "ar", "zh"]),
            )

            self._converter = DocumentConverter(pdf_options=pdf_opts)
            logger.info("Docling pipeline initialised")

        except ImportError as e:
            raise RuntimeError(
                f"Docling not installed: {e}. "
                f"Install: pip install docling==2.5.0"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Docling init failed: {e}") from e

    def parse(
        self,
        file_bytes: bytes,
        mime_type: str,
        source_filename: str,
        max_pages: int = 500,
    ) -> list[ParsedElement]:
        """
        Parse document bytes into a flat list of ParsedElements in reading order.

        Parameters
        ----------
        file_bytes : raw file bytes (any supported format)
        mime_type : detected MIME type from validate_upload()
        source_filename : used only for logging
        max_pages : raise DocumentTooLargeError if exceeded

        Returns
        -------
        list[ParsedElement] in reading order, page 1 first

        Raises
        ------
        ParseFailedError : if Docling cannot extract any content
        DocumentTooLargeError : if page count exceeds max_pages
        """
        from core.exceptions import ParseFailedError, DocumentTooLargeError

        # Write to temp file — Docling requires a path, not bytes
        suffix = self._mime_to_suffix(mime_type)
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                f.write(file_bytes)
                tmp_path = f.name

            result = self._converter.convert(tmp_path)
            doc    = result.document

            # Page count check
            page_count = self._count_pages(doc)
            if page_count > max_pages:
                raise DocumentTooLargeError(page_count, max_pages, "pages")

            elements = self._extract_elements(doc)

            if not elements:
                raise ParseFailedError("unknown", "Docling extracted 0 elements")

            logger.info(
                f"Parsed '{source_filename}': {page_count} pages, "
                f"{len(elements)} elements "
                f"({sum(1 for e in elements if e.element_type == ElementType.TABLE)} tables, "
                f"{sum(1 for e in elements if e.element_type == ElementType.FIGURE)} figures)"
            )
            return elements

        except (DocumentTooLargeError, ParseFailedError):
            raise
        except Exception as e:
            from core.exceptions import ParseFailedError
            logger.error(f"Docling parse error for '{source_filename}': {e}", exc_info=True)
            raise ParseFailedError("unknown", str(e)) from e
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def _count_pages(self, doc) -> int:
        """Count pages in a Docling document."""
        try:
            return len(doc.pages)
        except Exception:
            return 1

    def _extract_elements(self, doc) -> list[ParsedElement]:
        """
        Walk Docling document tree and produce ParsedElement list.
        Maintains a heading stack to build section_path breadcrumbs.
        """
        elements: list[ParsedElement] = []
        heading_stack: list[str] = []   # Stack of heading text at each level

        try:
            # Docling document body items
            items = list(doc.iterate_items())
        except AttributeError:
            # Fallback for older Docling versions
            items = getattr(doc, 'body', {})
            if hasattr(items, 'children'):
                items = list(self._flatten_children(items.children))
            else:
                return self._fallback_extraction(doc)

        for item, level in items:
            try:
                elem = self._item_to_element(item, level, heading_stack, doc)
                if elem:
                    if elem.element_type == ElementType.HEADING:
                        # Truncate heading stack to current level and push
                        heading_stack = heading_stack[:elem.heading_level - 1]
                        heading_stack.append(elem.text)
                    elem.section_path = list(heading_stack)
                    elements.append(elem)
            except Exception as e:
                logger.debug(f"Skipping element due to error: {e}")

        return elements

    def _flatten_children(self, children) -> list:
        """Recursively flatten nested Docling children."""
        result = []
        for child in (children or []):
            result.append((child, 0))
            sub = getattr(child, 'children', [])
            if sub:
                result.extend(self._flatten_children(sub))
        return result

    def _item_to_element(self, item, level, heading_stack: list[str], doc) -> Optional[ParsedElement]:
        """Convert one Docling item to a ParsedElement."""
        # Docling uses different class names depending on version
        cls_name = type(item).__name__

        # Get page number safely
        page_no = 1
        try:
            if hasattr(item, 'prov') and item.prov:
                page_no = item.prov[0].page_no if hasattr(item.prov[0], 'page_no') else 1
        except Exception:
            pass

        # Heading
        if cls_name in ('SectionHeaderItem',) or (hasattr(item, 'label') and 'heading' in str(getattr(item, 'label', '')).lower()):
            text = getattr(item, 'text', '') or ''
            lvl  = getattr(item, 'level', 1) or 1
            if text.strip():
                return ParsedElement(
                    element_type=ElementType.HEADING,
                    text=text.strip(),
                    page_number=page_no,
                    heading_level=int(lvl),
                )

        # Table
        if cls_name == 'TableItem' or (hasattr(item, 'label') and 'table' in str(getattr(item, 'label', '')).lower()):
            text = ""
            try:
                text = item.export_to_markdown() or ""
            except Exception:
                pass
            return ParsedElement(
                element_type=ElementType.TABLE,
                text=text,
                page_number=page_no,
                table_data=None,   # Populated by table_extractor.py in orchestrator
            )

        # Figure / Picture
        if cls_name in ('PictureItem', 'FigureItem') or (hasattr(item, 'label') and 'picture' in str(getattr(item, 'label', '')).lower()):
            image_bytes = None
            caption     = None
            try:
                img = item.get_image(doc)
                if img:
                    import io
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    image_bytes = buf.getvalue()
                caption = str(item.caption) if hasattr(item, 'caption') and item.caption else None
            except Exception as e:
                logger.debug(f"Image extraction failed: {e}")

            return ParsedElement(
                element_type=ElementType.FIGURE,
                text="",
                page_number=page_no,
                image_bytes=image_bytes,
                image_caption=caption,
            )

        # List items
        if cls_name in ('ListItem',) or (hasattr(item, 'label') and 'list' in str(getattr(item, 'label', '')).lower()):
            text = getattr(item, 'text', '') or ''
            if text.strip():
                return ParsedElement(
                    element_type=ElementType.LIST_ITEM,
                    text=text.strip(),
                    page_number=page_no,
                )

        # Caption / Footnote
        label_str = str(getattr(item, 'label', '')).lower()
        if 'caption' in label_str:
            text = getattr(item, 'text', '') or ''
            return ParsedElement(element_type=ElementType.CAPTION, text=text.strip(), page_number=page_no)
        if 'footnote' in label_str:
            text = getattr(item, 'text', '') or ''
            return ParsedElement(element_type=ElementType.FOOTNOTE, text=text.strip(), page_number=page_no)

        # Page header/footer — mark for skipping
        if 'page_header' in label_str or 'header' in label_str:
            return ParsedElement(element_type=ElementType.PAGE_HEADER, text="", page_number=page_no)
        if 'page_footer' in label_str or 'footer' in label_str:
            return ParsedElement(element_type=ElementType.PAGE_FOOTER, text="", page_number=page_no)

        # Default: paragraph text
        text = getattr(item, 'text', '') or ''
        if text.strip():
            return ParsedElement(
                element_type=ElementType.PARAGRAPH,
                text=text.strip(),
                page_number=page_no,
            )

        return None

    def _fallback_extraction(self, doc) -> list[ParsedElement]:
        """
        Fallback: export to markdown and parse structure from that.
        Used when Docling's item-level API is unavailable.
        Less accurate (no per-element page numbers) but always works.
        """
        elements = []
        try:
            md = doc.export_to_markdown()
            heading_stack = []
            for line in md.split('\n'):
                stripped = line.strip()
                if not stripped:
                    continue

                if stripped.startswith('# '):
                    text = stripped[2:].strip()
                    heading_stack = [text]
                    elements.append(ParsedElement(
                        element_type=ElementType.HEADING, text=text,
                        page_number=1, heading_level=1, section_path=[text]
                    ))
                elif stripped.startswith('## '):
                    text = stripped[3:].strip()
                    heading_stack = heading_stack[:1] + [text]
                    elements.append(ParsedElement(
                        element_type=ElementType.HEADING, text=text,
                        page_number=1, heading_level=2, section_path=list(heading_stack)
                    ))
                elif stripped.startswith('### '):
                    text = stripped[4:].strip()
                    heading_stack = heading_stack[:2] + [text]
                    elements.append(ParsedElement(
                        element_type=ElementType.HEADING, text=text,
                        page_number=1, heading_level=3, section_path=list(heading_stack)
                    ))
                elif stripped.startswith('|') and '|' in stripped[1:]:
                    elements.append(ParsedElement(
                        element_type=ElementType.TABLE, text=stripped,
                        page_number=1, section_path=list(heading_stack)
                    ))
                elif stripped.startswith(('- ', '* ', '+ ')):
                    elements.append(ParsedElement(
                        element_type=ElementType.LIST_ITEM, text=stripped[2:].strip(),
                        page_number=1, section_path=list(heading_stack)
                    ))
                else:
                    elements.append(ParsedElement(
                        element_type=ElementType.PARAGRAPH, text=stripped,
                        page_number=1, section_path=list(heading_stack)
                    ))
        except Exception as e:
            logger.error(f"Fallback extraction failed: {e}")
        return elements

    @staticmethod
    def _mime_to_suffix(mime_type: str) -> str:
        suffixes = {
            "application/pdf": ".pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
            "text/plain": ".txt",
            "text/markdown": ".md",
            "text/csv": ".csv",
        }
        return suffixes.get(mime_type, ".bin")
