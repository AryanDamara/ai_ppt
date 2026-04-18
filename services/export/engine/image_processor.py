"""
Image processor — fetch images from S3/URLs and apply visual treatments.

Treatments:
  original           → no transformation
  monochrome         → convert to greyscale, then back to RGB for Pillow
  duotone            → two-color tone-mapping (theme accent_primary + background)
  gradient_overlay   → linear gradient overlay blended onto the image
"""
from __future__ import annotations
import logging
from io import BytesIO
from typing import Optional

logger = logging.getLogger(__name__)


class ImageProcessor:

    def fetch(self, uri: str) -> bytes:
        """
        Fetch image bytes from a URI (S3 pre-signed URL or public URL).
        Uses httpx with a 10-second timeout and 3 retries.
        Raises AssetFetchError on failure.
        """
        from core.exceptions import AssetFetchError
        import httpx
        from tenacity import retry, stop_after_attempt, wait_fixed

        @retry(stop=stop_after_attempt(3), wait=wait_fixed(1), reraise=True)
        def _fetch() -> bytes:
            with httpx.Client(timeout=10.0, follow_redirects=True) as client:
                resp = client.get(uri)
                resp.raise_for_status()
                return resp.content

        try:
            return _fetch()
        except Exception as exc:
            raise AssetFetchError(f"Failed to fetch image from '{uri}': {exc}") from exc

    def apply_treatment(self, image_bytes: bytes, treatment: str) -> bytes:
        """
        Apply a visual treatment to image bytes using Pillow.
        Returns the processed image as PNG bytes.

        Parameters
        ----------
        image_bytes : raw image bytes (any format Pillow supports)
        treatment   : "original" | "monochrome" | "duotone" | "gradient_overlay"
        """
        if treatment == "original":
            return image_bytes

        from PIL import Image, ImageOps, ImageFilter
        img = Image.open(BytesIO(image_bytes)).convert("RGBA")

        if treatment == "monochrome":
            img = ImageOps.grayscale(img).convert("RGBA")

        elif treatment == "duotone":
            # Map luminance to a two-color ramp: dark→accent_primary, light→white
            grey  = ImageOps.grayscale(img)
            dark  = (79, 70, 229, 255)   # Indigo (accent_primary fallback)
            light = (255, 255, 255, 255)
            duotone = Image.new("RGBA", img.size)
            for px_y in range(img.height):
                for px_x in range(img.width):
                    lum = grey.getpixel((px_x, px_y)) / 255.0
                    r = int(dark[0] + lum * (light[0] - dark[0]))
                    g = int(dark[1] + lum * (light[1] - dark[1]))
                    b = int(dark[2] + lum * (light[2] - dark[2]))
                    duotone.putpixel((px_x, px_y), (r, g, b, 255))
            img = duotone

        elif treatment == "gradient_overlay":
            from PIL import ImageDraw
            overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
            draw    = ImageDraw.Draw(overlay)
            for py in range(img.height):
                alpha = int((py / img.height) * 180)  # 0 → 180 alpha
                draw.line([(0, py), (img.width, py)], fill=(0, 0, 0, alpha))
            img = Image.alpha_composite(img.convert("RGBA"), overlay)

        output = BytesIO()
        img.save(output, format="PNG")
        output.seek(0)
        return output.read()
