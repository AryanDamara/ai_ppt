"""
Module 2 — Font Metrics Engine (HarfBuzz-Aware)
Parses font files and measures text with kerning, ligatures, and complex script support.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Tuple, List
from pathlib import Path

try:
    from fontTools.ttLib import TTFont
    import freetype
    import uharfbuzz as hb
    import numpy as np
    FONTTOOLS_AVAILABLE = True
except ImportError:
    FONTTOOLS_AVAILABLE = False


@dataclass
class FontMetrics:
    family_name: str
    style_name: str
    units_per_em: int
    ascender: int
    descender: int
    line_gap: int
    x_height: int
    cap_height: int
    has_cjk_glyphs: bool = False
    has_arabic_glyphs: bool = False
    is_monospaced: bool = False
    advance_width_cache: Dict[str, float] = field(default_factory=dict)
    avg_char_advance: float = 0.0
    hb_font_path: Optional[str] = None

    @property
    def line_height_units(self) -> int:
        return (self.ascender - self.descender) + self.line_gap

    def scale_factor(self, font_size_px: float) -> float:
        return font_size_px / self.units_per_em

    def line_height_px(self, font_size_px: float, line_height_multiplier: float = 1.2) -> float:
        cap_height_px = self.cap_height * self.scale_factor(font_size_px)
        return cap_height_px * line_height_multiplier


class FontMetricsParser:
    PRECOMPUTE_CHARS = (
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
        "0123456789 .,;:!?-\u2013\u2014()[]\"'"
    )

    def parse(self, font_path: str | Path) -> FontMetrics:
        if not FONTTOOLS_AVAILABLE:
            return self._fallback_metrics(font_path)

        font_path = Path(font_path)
        if not font_path.exists():
            raise FileNotFoundError(f"Font file not found: {font_path}")

        try:
            tt_font = TTFont(str(font_path))
            os2 = tt_font.get('OS/2')
            head = tt_font['head']
            name = tt_font['name']

            units_per_em = head.unitsPerEm

            if os2 and hasattr(os2, 'sTypoAscender') and os2.sTypoAscender != 0:
                ascender = os2.sTypoAscender
                descender = os2.sTypoDescender
                line_gap = os2.sTypoLineGap
            else:
                hhea = tt_font['hhea']
                ascender = hhea.ascender
                descender = hhea.descender
                line_gap = hhea.lineGap

            x_height = getattr(os2, 'sxHeight', int(ascender * 0.52)) if os2 else int(ascender * 0.52)
            cap_height = getattr(os2, 'sCapHeight', int(ascender * 0.72)) if os2 else int(ascender * 0.72)

            cmap = tt_font.getBestCmap() or {}
            has_cjk = any(0x4E00 <= cp <= 0x9FFF for cp in cmap.keys())
            has_arabic = any(0x0600 <= cp <= 0x06FF for cp in cmap.keys())

            hmtx = tt_font['hmtx'].metrics
            advance_widths = [aw for _, (aw, _) in hmtx.items() if aw > 0]
            is_mono = len(set(advance_widths)) == 1 if advance_widths else False

            family = self._get_name_string(name, 1) or font_path.stem
            style = self._get_name_string(name, 2) or "Regular"

            # Glyph-level advance widths via freetype
            advance_cache: Dict[str, float] = {}
            total_advance = 0.0
            count = 0

            try:
                face = freetype.Face(str(font_path))
                face.set_char_size(units_per_em * 64)

                for char in self.PRECOMPUTE_CHARS:
                    glyph_index = face.get_char_index(char)
                    if glyph_index == 0:
                        continue
                    face.load_glyph(glyph_index, freetype.FT_LOAD_NO_SCALE)
                    advance = face.glyph.metrics.horiAdvance
                    advance_cache[char] = float(advance)
                    total_advance += advance
                    count += 1

                avg_advance = total_advance / count if count > 0 else units_per_em * 0.6
            except Exception:
                advance_cache = {}
                avg_advance = units_per_em * 0.6

            tt_font.close()

            return FontMetrics(
                family_name=family,
                style_name=style,
                units_per_em=units_per_em,
                ascender=ascender,
                descender=descender,
                line_gap=line_gap,
                x_height=x_height,
                cap_height=cap_height,
                has_cjk_glyphs=has_cjk,
                has_arabic_glyphs=has_arabic,
                is_monospaced=is_mono,
                advance_width_cache=advance_cache,
                avg_char_advance=avg_advance,
                hb_font_path=str(font_path) if (has_arabic or has_cjk) else None,
            )
        except Exception as e:
            raise RuntimeError(f"Failed to parse font {font_path}: {e}")

    def _fallback_metrics(self, font_path: str | Path) -> FontMetrics:
        """Fallback when fontTools is not available."""
        font_path = Path(font_path)
        return FontMetrics(
            family_name=font_path.stem,
            style_name="Regular",
            units_per_em=1000,
            ascender=800,
            descender=-200,
            line_gap=200,
            x_height=500,
            cap_height=700,
            has_cjk_glyphs=False,
            has_arabic_glyphs=False,
            is_monospaced=False,
            advance_width_cache={},
            avg_char_advance=600,
            hb_font_path=None,
        )

    def _get_name_string(self, name_table, name_id: int) -> Optional[str]:
        try:
            record = name_table.getName(name_id, 3, 1, 0x0409)
            if record:
                return record.toUnicode()
            record = name_table.getName(name_id, 1, 0, 0)
            if record:
                return record.toUnicode()
        except Exception:
            pass
        return None


class TextMeasurer:
    """Measures text bounding boxes with HarfBuzz for complex scripts."""

    def measure(
        self,
        text: str,
        font_metrics: FontMetrics,
        font_size_px: float,
        max_width_px: float,
        line_height_multiplier: float = 1.2,
        script: str = "latin",
        is_bidi: bool = False,
    ) -> Tuple[float, float]:
        """
        Measure text with line wrapping.
        Returns (width_px, height_px).
        """
        if not text:
            return (0.0, font_metrics.line_height_px(font_size_px, line_height_multiplier))

        if (script == "rtl" or is_bidi) and font_metrics.hb_font_path:
            lines = self._measure_with_harfbuzz(text, font_metrics, font_size_px, max_width_px)
        elif script == "cjk":
            lines = self._measure_cjk(text, font_metrics, font_size_px, max_width_px)
        else:
            lines = self._measure_latin(text, font_metrics, font_size_px, max_width_px)

        line_height_px = font_metrics.line_height_px(font_size_px, line_height_multiplier)
        return (max_width_px, lines * line_height_px)

    def _measure_with_harfbuzz(
        self,
        text: str,
        metrics: FontMetrics,
        font_size_px: float,
        max_width_px: float,
    ) -> int:
        """Use HarfBuzz for accurate text shaping (Arabic, BiDi, Devanagari)."""
        if not FONTTOOLS_AVAILABLE or not metrics.hb_font_path:
            return self._measure_latin(text, metrics, font_size_px, max_width_px)

        try:
            blob = hb.Blob.from_file_path(metrics.hb_font_path)
            face = hb.Face(blob)
            font = hb.Font(face)
            font.scale = (metrics.units_per_em, metrics.units_per_em)

            buf = hb.Buffer()
            buf.add_str(text)
            buf.guess_segment_properties()

            hb.shape(font, buf)

            scale = metrics.scale_factor(font_size_px)
            total_advance = sum(info.x_advance for info in buf.glyph_positions) * scale

            lines = max(1, int(total_advance / max_width_px) + 1)
            return lines

        except Exception:
            return self._measure_latin(text, metrics, font_size_px, max_width_px)

    def _measure_latin(self, text: str, metrics: FontMetrics, font_size_px: float, max_width_px: float) -> int:
        scale = metrics.scale_factor(font_size_px)
        space_advance = metrics.advance_width_cache.get(' ', metrics.avg_char_advance) * scale

        words = text.split()
        if not words:
            return 1

        lines = 1
        current_width = 0.0

        for word in words:
            word_width = sum(
                metrics.advance_width_cache.get(c, metrics.avg_char_advance) * scale
                for c in word
            )
            if current_width == 0.0:
                current_width = word_width
            elif current_width + space_advance + word_width <= max_width_px:
                current_width += space_advance + word_width
            else:
                lines += 1
                current_width = word_width

        return lines

    def _measure_cjk(self, text: str, metrics: FontMetrics, font_size_px: float, max_width_px: float) -> int:
        scale = metrics.scale_factor(font_size_px)
        char_width = metrics.units_per_em * scale
        chars_per_line = max(1, int(max_width_px / char_width))
        return max(1, (len(text) + chars_per_line - 1) // chars_per_line)