"""
OCR fallback — Tesseract for scanned/image-only pages.

WHEN THIS RUNS:
  Docling attempts OCR automatically when it detects pages with no text layer.
  This module is a FALLBACK for when Docling's built-in OCR fails or produces
  poor results (low confidence, garbled text). The orchestrator calls this
  when a page's extracted text is suspiciously short (< 20 chars but the page
  exists in the document).

HOW IT WORKS:
  1. Convert PDF page to a high-DPI image (300 DPI via poppler/pdf2image)
  2. Pre-process: grayscale, deskew, contrast enhancement
  3. Run Tesseract with configurable language packs (eng, ara, chi_sim, etc.)
  4. Return extracted text with a confidence score

SYSTEM DEPENDENCIES:
  - tesseract-ocr (apt package)
  - tesseract-ocr-eng, tesseract-ocr-ara, tesseract-ocr-chi-sim (language packs)
  - poppler-utils (for pdf2image conversion)
  All installed in the Dockerfile.

OUTPUT:
  OCRResult with text, confidence, language, and page_number.
  Confidence < 0.3 → discard (likely a decorative page or blank page).
"""
from __future__ import annotations
import io
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class OCRResult:
    """Result from OCR processing of one page."""
    text:        str
    confidence:  float    # 0.0–1.0 (Tesseract reports 0–100, we normalise)
    language:    str      # BCP-47 code used for OCR
    page_number: int
    method:      str = "tesseract"


# Tesseract language code mapping (BCP-47 → Tesseract)
_LANG_MAP = {
    "en": "eng",
    "ar": "ara",
    "zh": "chi_sim",
    "de": "deu",
    "fr": "fra",
    "es": "spa",
    "ja": "jpn",
    "ko": "kor",
    "pt": "por",
    "ru": "rus",
    "it": "ita",
}


def ocr_image_bytes(
    image_bytes: bytes,
    language:    str = "en",
    page_number: int = 1,
    min_confidence: float = 0.3,
) -> Optional[OCRResult]:
    """
    Run Tesseract OCR on image bytes (PNG or JPEG).

    Parameters
    ----------
    image_bytes : raw image bytes (from Docling figure extraction or pdf2image)
    language : BCP-47 language code (maps to Tesseract lang pack)
    page_number : for metadata tracking
    min_confidence : discard results below this threshold

    Returns
    -------
    OCRResult or None if confidence too low or no text extracted
    """
    if not image_bytes or len(image_bytes) < 500:
        return None

    try:
        import pytesseract
        from PIL import Image, ImageEnhance, ImageFilter

        # Load image
        img = Image.open(io.BytesIO(image_bytes))

        # Pre-processing pipeline for better OCR accuracy
        img = _preprocess_for_ocr(img)

        # Map language code
        tess_lang = _LANG_MAP.get(language[:2].lower(), "eng")

        # Run Tesseract with detailed output (includes confidence)
        data = pytesseract.image_to_data(
            img,
            lang=tess_lang,
            output_type=pytesseract.Output.DICT,
            config="--psm 6 --oem 3",   # PSM 6: assume uniform block of text
        )

        # Extract text and compute average confidence
        words = []
        confidences = []
        for i, word in enumerate(data.get("text", [])):
            conf = data["conf"][i]
            if isinstance(conf, str):
                try:
                    conf = float(conf)
                except ValueError:
                    continue
            if conf > 0 and word.strip():
                words.append(word.strip())
                confidences.append(conf)

        if not words:
            return None

        text = " ".join(words)
        avg_confidence = sum(confidences) / len(confidences) / 100.0  # Normalise to 0–1

        if avg_confidence < min_confidence:
            logger.debug(
                f"OCR confidence too low ({avg_confidence:.2f}) on page {page_number}. "
                f"Discarding {len(words)} words."
            )
            return None

        return OCRResult(
            text=text,
            confidence=round(avg_confidence, 3),
            language=language,
            page_number=page_number,
        )

    except ImportError:
        logger.warning("pytesseract not installed. OCR fallback unavailable.")
        return None
    except Exception as e:
        logger.error(f"OCR failed on page {page_number}: {e}")
        return None


def ocr_pdf_page(
    pdf_bytes: bytes,
    page_number: int,
    language: str = "en",
    dpi: int = 300,
) -> Optional[OCRResult]:
    """
    Extract a single page from a PDF and run OCR on it.

    Uses pdf2image (poppler) to render the page as a high-DPI image,
    then runs Tesseract OCR on the rendered image.

    Parameters
    ----------
    pdf_bytes : full PDF file bytes
    page_number : 1-indexed page to OCR
    language : BCP-47 code
    dpi : rendering resolution (300 = good balance of quality vs. speed)

    Returns
    -------
    OCRResult or None
    """
    try:
        from pdf2image import convert_from_bytes

        # Render just the requested page
        images = convert_from_bytes(
            pdf_bytes,
            first_page=page_number,
            last_page=page_number,
            dpi=dpi,
            fmt="png",
        )

        if not images:
            return None

        # Convert PIL Image to bytes
        buf = io.BytesIO()
        images[0].save(buf, format="PNG")
        image_bytes = buf.getvalue()

        return ocr_image_bytes(
            image_bytes=image_bytes,
            language=language,
            page_number=page_number,
        )

    except ImportError:
        logger.warning("pdf2image not installed. PDF OCR fallback unavailable.")
        return None
    except Exception as e:
        logger.error(f"PDF OCR failed on page {page_number}: {e}")
        return None


def _preprocess_for_ocr(img) -> "Image":
    """
    Apply preprocessing to improve OCR accuracy.

    Steps:
    1. Convert to grayscale (removes colour channel noise)
    2. Increase contrast (makes text sharper against background)
    3. Apply light sharpening (counteracts scan blur)
    4. Resize if image is very small (Tesseract needs ~300 DPI equivalent)
    """
    from PIL import Image, ImageEnhance, ImageFilter

    # Grayscale
    if img.mode != "L":
        img = img.convert("L")

    # Enhance contrast
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.5)

    # Sharpen
    img = img.filter(ImageFilter.SHARPEN)

    # Upscale small images (Tesseract needs reasonable resolution)
    min_dim = min(img.size)
    if min_dim < 600:
        scale = max(2, 1200 // min_dim)
        img = img.resize(
            (img.size[0] * scale, img.size[1] * scale),
            Image.LANCZOS,
        )

    return img
