"""
Font embedder — injects TTF/OTF font files into the PPTX archive.

Without font embedding, a presentation that uses Inter or Playfair Display
will display in the fallback system font (usually Calibri or Arial) on any
machine that does not have those fonts installed. Embedded fonts travel with
the file.

python-pptx 0.6.23 does not expose a public API for font embedding.
We use ZIP-level injection into the ppt/fonts/ directory of the PPTX archive.
This is safe and widely used by other PPTX tools.
"""
from __future__ import annotations
import logging
from pathlib import Path

from engine.theme_resolver import ThemeTokens
from core.exceptions import FontEmbedError

logger = logging.getLogger(__name__)


class FontEmbedder:

    def embed_fonts(self, prs, tokens: ThemeTokens, font_dir: str = "/app/fonts") -> None:
        """
        Embed the theme's body and display fonts into the Presentation object.

        Each font is embedded exactly once (even if body == display).
        Failures are non-fatal: exports with a warning, uses system font fallback.
        """
        font_dir_path  = Path(font_dir)
        seen_paths: set[str] = set()

        for font_name, font_rel_path in [
            (tokens.body_font_name,    tokens.body_font_path),
            (tokens.display_font_name, tokens.display_font_path),
        ]:
            if font_rel_path in seen_paths:
                continue  # Don't embed the same file twice
            seen_paths.add(font_rel_path)

            full_path = font_dir_path / font_rel_path
            if not full_path.exists():
                logger.warning(
                    f"Font '{font_name}' not found at {full_path}. "
                    f"The exported PPTX will use system font fallback. "
                    f"Run scripts/download_fonts.py to fetch required fonts."
                )
                continue

            try:
                self._embed_via_zip(prs, font_name, full_path)
                logger.debug(f"Embedded font: {font_name} ({full_path.name})")
            except FontEmbedError as e:
                logger.warning(f"Font embed failed for '{font_name}': {e}")

    def _embed_via_zip(self, prs, font_name: str, font_path: Path) -> None:
        """
        Inject font bytes into the PPTX ZIP archive at ppt/fonts/{filename}.
        """
        font_bytes = font_path.read_bytes()
        zip_path   = f"ppt/fonts/{font_path.name}"

        # Access the underlying ZIP package — works in python-pptx 0.6.x
        package = prs.part.package
        if not hasattr(package, '_zip'):
            raise FontEmbedError(
                f"Cannot access PPTX ZIP package for font embedding. "
                f"This is expected if python-pptx version changes."
            )

        try:
            package._zip.writestr(zip_path, font_bytes)
        except Exception as exc:
            raise FontEmbedError(f"ZIP writestr failed for {zip_path}: {exc}") from exc
