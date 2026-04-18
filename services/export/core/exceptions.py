class ExportValidationError(Exception):
    """
    Raised when deck JSON has blocking errors that prevent export.
    Returns HTTP 422 to the caller. Export must NOT proceed.
    """
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"Export blocked by {len(errors)} validation error(s): {errors[:3]}")


class SlideExportError(Exception):
    """
    Raised when ONE slide builder fails.
    Non-fatal at the renderer level — adds error placeholder slide and continues.
    """
    def __init__(self, slide_id: str, slide_index: int, reason: str):
        self.slide_id    = slide_id
        self.slide_index = slide_index
        self.reason      = reason
        super().__init__(f"Slide {slide_index} ({slide_id[:8]}…): {reason}")


class ChartDataError(Exception):
    """
    Raised when chart data is malformed (e.g. string values instead of numbers).
    Caught by data_chart builder — exports error text box instead of crashing.
    """
    pass


class SVGConversionError(Exception):
    """
    Raised when SVG → DrawingML conversion fails.
    The SVG converter falls back to 300 DPI PNG on this error.
    """
    pass


class AssetFetchError(Exception):
    """
    Raised when an image/asset cannot be fetched from S3 or URL.
    The visual_split builder renders a placeholder rectangle instead.
    """
    pass


class FontEmbedError(Exception):
    """
    Raised when a font file is not found for embedding.
    Non-fatal — export continues with system font fallback (logs warning).
    """
    pass
