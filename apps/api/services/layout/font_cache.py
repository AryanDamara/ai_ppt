"""
Module 3 — Font Cache with LRU Eviction
LRU-cached font metrics to prevent memory bloat in long-running servers.
"""

from pathlib import Path
from typing import Dict, Optional
from .font_metrics import FontMetrics, FontMetricsParser

try:
    from cachetools import LRUCache
    CACHE_AVAILABLE = True
except ImportError:
    CACHE_AVAILABLE = False

FONT_DIR = Path(__file__).parent.parent.parent / "fonts"

# LRU cache: max 50 fonts ≈ 200MB memory ceiling
if CACHE_AVAILABLE:
    _cache: LRUCache = LRUCache(maxsize=50)
else:
    _cache: Dict[str, FontMetrics] = {}

THEME_FONT_MAP: Dict[str, Dict[str, str]] = {
    "corporate_dark":     {"body": "inter/Inter-Regular.ttf",    "display": "inter/Inter-Bold.ttf"},
    "modern_light":       {"body": "inter/Inter-Regular.ttf",    "display": "playfair/PlayfairDisplay-Regular.ttf"},
    "startup_minimal":    {"body": "inter/Inter-Regular.ttf",    "display": "inter/Inter-Bold.ttf"},
    "healthcare_clinical":{"body": "inter/Inter-Regular.ttf",    "display": "inter/Inter-Bold.ttf"},
    "financial_formal":   {"body": "inter/Inter-Regular.ttf",    "display": "playfair/PlayfairDisplay-Regular.ttf"},
}

LANGUAGE_FONT_MAP: Dict[str, Dict[str, str]] = {
    "zh": {"body": "noto/NotoSansCJKsc-Regular.otf", "script": "cjk"},
    "ja": {"body": "noto/NotoSansCJKjp-Regular.otf", "script": "cjk"},
    "ko": {"body": "noto/NotoSansCJKjp-Regular.otf", "script": "cjk"},
    "ar": {"body": "noto/NotoNaskhArabic-Regular.ttf", "script": "rtl"},
    "he": {"body": "noto/NotoNaskhArabic-Regular.ttf", "script": "rtl"},
    "fa": {"body": "noto/NotoNaskhArabic-Regular.ttf", "script": "rtl"},
}

FONT_FALLBACK_CHAIN: Dict[str, list] = {
    "inter/Inter-Regular.ttf": [
        "inter/Inter-Regular.ttf",
        "/usr/share/fonts/truetype/arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Windows/Fonts/arial.ttf",
    ],
    "playfair/PlayfairDisplay-Regular.ttf": [
        "playfair/PlayfairDisplay-Regular.ttf",
        "inter/Inter-Bold.ttf",
    ],
}

_parser = FontMetricsParser()


def get_font_metrics(font_path: str, allow_fallback: bool = True) -> FontMetrics:
    """
    Get font metrics. LRU-cached. Falls back to system fonts if file is missing.
    """
    if font_path in _cache:
        return _cache[font_path]

    full_path = FONT_DIR / font_path

    if not full_path.exists() and allow_fallback:
        fallbacks = FONT_FALLBACK_CHAIN.get(font_path, [])
        for fallback in fallbacks:
            candidate = Path(fallback) if fallback.startswith('/') else FONT_DIR / fallback
            if candidate.exists():
                import logging
                logging.getLogger(__name__).warning(
                    f"Font {font_path} not found, using fallback: {fallback}"
                )
                metrics = _parser.parse(candidate)
                _cache[font_path] = metrics
                return metrics

        raise FileNotFoundError(
            f"Font {font_path} not found and no fallback available. "
            f"Run: python scripts/download_fonts.py"
        )

    metrics = _parser.parse(full_path)
    _cache[font_path] = metrics
    return metrics


def get_theme_fonts(theme: str, language: str = "en") -> Dict:
    lang_prefix = language.split("-")[0].lower()

    if lang_prefix in LANGUAGE_FONT_MAP:
        lang_info = LANGUAGE_FONT_MAP[lang_prefix]
        body = get_font_metrics(lang_info["body"])
        return {"body": body, "display": body, "script": lang_info["script"]}

    theme_fonts = THEME_FONT_MAP.get(theme, THEME_FONT_MAP["modern_light"])
    return {
        "body": get_font_metrics(theme_fonts["body"]),
        "display": get_font_metrics(theme_fonts["display"]),
        "script": "latin",
    }


def preload_all_fonts() -> None:
    """Preload fonts on startup. Non-fatal if fonts are missing."""
    for font_map in THEME_FONT_MAP.values():
        for path in font_map.values():
            if path not in _cache:
                try:
                    get_font_metrics(path)
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"Preload failed for {path}: {e}")

    for lang_info in LANGUAGE_FONT_MAP.values():
        path = lang_info["body"]
        if path not in _cache:
            try:
                get_font_metrics(path)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Preload failed for {path}: {e}")


def get_cache_stats() -> Dict:
    if CACHE_AVAILABLE:
        return {
            "size": len(_cache),
            "maxsize": _cache.maxsize,
            "currsize": _cache.currsize,
        }
    return {"size": len(_cache), "maxsize": 50, "currsize": len(_cache)}