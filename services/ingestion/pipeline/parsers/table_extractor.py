"""
Table extractor — preserves row/column relationships in structured JSON.

WHY TWO CHUNKS PER TABLE:
  chunk_type=table_json    → enables exact lookup: "What was Q3 revenue?"
                              LLM sees: [{"quarter": "Q3", "revenue": "$6.8M"}]
                              Can answer precisely from structured data.

  chunk_type=table_description → enables semantic lookup: "quarterly performance trends"
                              LLM sees: "Table: Revenue by Quarter. Q1 $4.2M (+12%). Q3 $6.8M (+33%)."
                              Found by semantic similarity even without exact terms.

  Using only one chunk type loses either precision or recall.
  Always produce both.
"""
from __future__ import annotations
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def extract_table_to_json(table_item) -> Optional[dict]:
    """
    Extract a Docling TableItem to a structured dict preserving row/column relationships.

    Returns:
      {"headers": [str], "rows": [{"header": "cell_value", ...}], "caption": str|None}
    Returns None if table has no extractable structure.
    """
    try:
        # Docling TableItem exposes .data.grid — a 2D array of TableCell objects
        data = getattr(table_item, 'data', None)
        if not data:
            return None

        grid = getattr(data, 'grid', None) or []
        if len(grid) < 2:   # Need at least header row + one data row
            return None

        # Extract headers from first row
        headers = []
        for cell in grid[0]:
            cell_text = getattr(cell, 'text', '') or ''
            headers.append(cell_text.strip() if cell_text.strip() else f"col_{len(headers)}")

        # Extract data rows
        rows = []
        for grid_row in grid[1:]:
            row_dict = {}
            for col_idx, cell in enumerate(grid_row):
                header   = headers[col_idx] if col_idx < len(headers) else f"col_{col_idx}"
                cell_txt = getattr(cell, 'text', '') or ''
                row_dict[header] = cell_txt.strip()
            # Only add row if at least one cell has content
            if any(v for v in row_dict.values()):
                rows.append(row_dict)

        if not rows:
            return None

        caption = None
        try:
            caption = str(table_item.caption) if getattr(table_item, 'caption', None) else None
        except Exception:
            pass

        return {"headers": headers, "rows": rows, "caption": caption}

    except Exception as e:
        logger.warning(f"Table JSON extraction failed: {e}")
        return None


def markdown_table_to_json(markdown_text: str) -> Optional[dict]:
    """
    Parse a Markdown-format table string to structured dict.
    Used when Docling returns markdown tables in its export_to_markdown() fallback.

    GFM table format:
    | Header A | Header B |
    |----------|----------|
    | Value 1  | Value 2  |
    | Value 3  | Value 4  |
    """
    lines = [l.strip() for l in markdown_text.strip().split('\n')]
    lines = [l for l in lines if l and l.startswith('|')]

    if len(lines) < 2:
        return None

    def parse_row(line: str) -> list[str]:
        # Split on | and strip leading/trailing empty cells
        parts = line.split('|')
        if parts and parts[0].strip() == '':
            parts = parts[1:]
        if parts and parts[-1].strip() == '':
            parts = parts[:-1]
        return [p.strip() for p in parts]

    headers    = parse_row(lines[0])
    if not headers:
        return None

    # Skip separator line (e.g. |---|---|)
    data_lines = [l for l in lines[2:] if l and not all(c in '-|: ' for c in l)]

    rows = []
    for line in data_lines:
        cells = parse_row(line)
        row   = {}
        for i, header in enumerate(headers):
            row[header] = cells[i] if i < len(cells) else ""
        if any(v for v in row.values()):
            rows.append(row)

    return {"headers": headers, "rows": rows, "caption": None} if rows else None


def generate_table_description(table_dict: dict) -> str:
    """
    Generate a natural-language description of a table for semantic search.

    This description gets embedded and enables queries like
    "quarterly revenue trends" to find the table even without exact word matches.

    Format:
      "Table: [caption]. Columns: [headers]. [Row summaries]. [Insight sentence]."
    """
    headers = table_dict.get("headers", [])
    rows    = table_dict.get("rows", [])
    caption = table_dict.get("caption") or ""

    parts = []

    if caption:
        parts.append(f"Table: {caption}.")

    if headers:
        parts.append(f"Columns: {', '.join(headers)}.")

    # Summarise rows (up to 15 rows for the description)
    row_summaries = []
    for row in rows[:15]:
        row_parts = [f"{k}: {v}" for k, v in row.items() if v and v.strip()]
        if row_parts:
            row_summaries.append(". ".join(row_parts))

    if row_summaries:
        parts.append(" | ".join(row_summaries))

    if len(rows) > 15:
        parts.append(f"(Table continues — {len(rows) - 15} more rows not shown.)")

    if not parts:
        return "Table with no extractable text content."

    return " ".join(parts)


def table_item_to_text(table_item) -> str:
    """
    Fast text extraction from a Docling TableItem when structured extraction
    is not needed (e.g., for the markdown representation).
    """
    try:
        return table_item.export_to_markdown() or ""
    except Exception:
        return ""
