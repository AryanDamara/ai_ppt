"""
Grid System — 12-column responsive grid for slide layouts.
"""

from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class GridCell:
    x: int
    y: int
    width: int
    height: int
    col_start: int
    col_end: int
    row_start: int
    row_end: int


class GridSystem:
    """12-column grid with configurable row count."""

    COLS = 12
    GUTTER = 16  # layout units
    MARGIN = 60  # layout units

    def __init__(self, slide_width: int = 1000, slide_height: int = 562, rows: int = 6):
        self.slide_width = slide_width
        self.slide_height = slide_height
        self.rows = rows
        self.col_width = (slide_width - 2 * self.MARGIN - (self.COLS - 1) * self.GUTTER) // self.COLS
        self.row_height = (slide_height - 2 * self.MARGIN) // rows

    def get_cell(self, col_start: int, col_span: int, row_start: int, row_span: int) -> GridCell:
        """Get grid cell coordinates."""
        x = self.MARGIN + col_start * (self.col_width + self.GUTTER)
        y = self.MARGIN + row_start * self.row_height
        width = col_span * self.col_width + (col_span - 1) * self.GUTTER
        height = row_span * self.row_height
        return GridCell(
            x=x, y=y, width=width, height=height,
            col_start=col_start, col_end=col_start + col_span,
            row_start=row_start, row_end=row_start + row_span
        )

    def split_columns(self, count: int, margin_override: int = None) -> List[Tuple[int, int]]:
        """Split available width into equal columns."""
        margin = margin_override if margin_override is not None else self.MARGIN
        available = self.slide_width - 2 * margin
        if count == 1:
            return [(margin, available)]

        col_w = (available - (count - 1) * self.GUTTER) // count
        columns = []
        for i in range(count):
            x = margin + i * (col_w + self.GUTTER)
            columns.append((x, col_w))
        return columns