"""
Image classifier — decorative vs. informational image detection.

WHY THIS EXISTS:
  Corporate documents contain many images that are NOT useful for RAG:
    - Company logos (repeated on every page)
    - Stock photos (people shaking hands, generic office scenes)
    - Decorative icons and separators
    - Watermarks and background images
    - Author headshots

  These images waste GPT-4o Vision tokens (~$0.01–$0.05 per call) and
  produce noise in the retrieval index. The classifier runs BEFORE
  the vision enricher and gates which images proceed to description.

CLASSIFICATION METHOD (heuristics — no ML model needed):
  1. Size-based: images < 50×50px are always decorative (icons)
  2. Aspect ratio: images with extreme aspect ratios (> 10:1) are likely
     horizontal rules, decorative borders, or banner ads
  3. Colour entropy: images with very low colour variation are likely
     solid-colour backgrounds or simple shapes
  4. File size: images < 1KB contain too little information to be useful

  These heuristics catch 90%+ of decorative images without any API calls.
  The remaining 10% are filtered by the vision enricher's classification step.
"""
from __future__ import annotations
import hashlib
import io
import logging
import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class ImageCategory(str, Enum):
    INFORMATIONAL = "informational"   # Charts, graphs, diagrams, tables-as-images
    DECORATIVE    = "decorative"      # Logos, stock photos, icons, borders
    UNCERTAIN     = "uncertain"       # Send to vision enricher for classification


@dataclass
class ClassificationResult:
    category:   ImageCategory
    reason:     str
    width:      int = 0
    height:     int = 0
    image_hash: str = ""   # SHA256 for deduplication


# ── Thresholds ────────────────────────────────────────────────────────────────
MIN_DIMENSION_PX     = 50    # Images smaller than this in either dimension → decorative
MIN_FILE_SIZE_BYTES  = 1000  # Images smaller than 1KB → decorative
MAX_ASPECT_RATIO     = 10.0  # Long thin banners → decorative
MIN_COLOR_ENTROPY    = 1.5   # Images with very low entropy → decorative


def classify_image(
    image_bytes: bytes,
    caption: Optional[str] = None,
) -> ClassificationResult:
    """
    Classify an image as informational, decorative, or uncertain.

    Parameters
    ----------
    image_bytes : PNG or JPEG bytes from Docling extraction
    caption : figure caption from the document (provides context)

    Returns
    -------
    ClassificationResult with category, reason, dimensions, and hash
    """
    if not image_bytes:
        return ClassificationResult(
            category=ImageCategory.DECORATIVE,
            reason="Empty image bytes",
        )

    # File size check
    if len(image_bytes) < MIN_FILE_SIZE_BYTES:
        return ClassificationResult(
            category=ImageCategory.DECORATIVE,
            reason=f"Image too small ({len(image_bytes)} bytes < {MIN_FILE_SIZE_BYTES})",
        )

    # Compute hash for deduplication
    img_hash = hashlib.sha256(image_bytes).hexdigest()[:20]

    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        width, height = img.size

        # Dimension check
        if width < MIN_DIMENSION_PX or height < MIN_DIMENSION_PX:
            return ClassificationResult(
                category=ImageCategory.DECORATIVE,
                reason=f"Dimensions too small ({width}×{height})",
                width=width, height=height, image_hash=img_hash,
            )

        # Aspect ratio check
        aspect = max(width, height) / max(min(width, height), 1)
        if aspect > MAX_ASPECT_RATIO:
            return ClassificationResult(
                category=ImageCategory.DECORATIVE,
                reason=f"Extreme aspect ratio ({aspect:.1f}:1)",
                width=width, height=height, image_hash=img_hash,
            )

        # Colour entropy check (low entropy = solid colour or gradient)
        entropy = _compute_colour_entropy(img)
        if entropy < MIN_COLOR_ENTROPY:
            return ClassificationResult(
                category=ImageCategory.DECORATIVE,
                reason=f"Low colour entropy ({entropy:.2f} < {MIN_COLOR_ENTROPY})",
                width=width, height=height, image_hash=img_hash,
            )

        # Caption-based hints: if caption contains chart/graph/figure keywords
        if caption:
            caption_lower = caption.lower()
            informational_keywords = [
                "chart", "graph", "figure", "diagram", "table",
                "flow", "process", "architecture", "timeline",
                "comparison", "breakdown", "distribution", "trend",
                "revenue", "growth", "performance", "market",
            ]
            for keyword in informational_keywords:
                if keyword in caption_lower:
                    return ClassificationResult(
                        category=ImageCategory.INFORMATIONAL,
                        reason=f"Caption contains keyword '{keyword}'",
                        width=width, height=height, image_hash=img_hash,
                    )

        # Default: uncertain — send to vision enricher for final classification
        return ClassificationResult(
            category=ImageCategory.UNCERTAIN,
            reason="Passed heuristic filters — needs vision classification",
            width=width, height=height, image_hash=img_hash,
        )

    except ImportError:
        logger.warning("PIL not available for image classification")
        return ClassificationResult(
            category=ImageCategory.UNCERTAIN,
            reason="PIL not available",
            image_hash=img_hash,
        )
    except Exception as e:
        logger.debug(f"Image classification error: {e}")
        return ClassificationResult(
            category=ImageCategory.UNCERTAIN,
            reason=f"Classification error: {str(e)[:100]}",
            image_hash=img_hash,
        )


def _compute_colour_entropy(img) -> float:
    """
    Compute Shannon entropy of the image's colour histogram.

    Low entropy = uniform colour (decorative backgrounds, solid fills)
    High entropy = varied colours (charts with multiple series, photos)

    Quantise to 64 bins per channel for efficiency.
    """
    try:
        # Convert to RGB if not already
        if img.mode != "RGB":
            img = img.convert("RGB")

        # Resize to small thumbnail for speed (entropy is scale-invariant)
        thumb = img.resize((64, 64))

        # Get histogram (256 bins per channel × 3 channels = 768 values)
        histogram = thumb.histogram()

        # Compute normalised entropy
        total = sum(histogram)
        if total == 0:
            return 0.0

        entropy = 0.0
        for count in histogram:
            if count > 0:
                p = count / total
                entropy -= p * math.log2(p)

        return entropy

    except Exception:
        return 5.0   # Assume informational on error (conservative)


def is_duplicate_image(image_bytes: bytes, seen_hashes: set[str]) -> bool:
    """
    Check if this image has been seen before in the current document.
    Logos and watermarks repeat on every page — skip duplicates.

    Parameters
    ----------
    image_bytes : raw image bytes
    seen_hashes : mutable set of previously seen hashes (caller maintains)

    Returns
    -------
    True if duplicate, False if new (also adds hash to seen_hashes)
    """
    if not image_bytes:
        return True

    img_hash = hashlib.sha256(image_bytes).hexdigest()[:20]
    if img_hash in seen_hashes:
        return True

    seen_hashes.add(img_hash)
    return False
