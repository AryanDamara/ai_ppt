import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_vision_enricher_skips_small_images():
    """Images below 1000 bytes should be skipped (likely artifacts)."""
    from pipeline.enrichers.vision_enricher import VisionEnricher

    with patch.object(VisionEnricher, "__init__", lambda x: None):
        enricher = VisionEnricher()
        result = await enricher.describe_image(b"\x89PNG" + b"\x00" * 10, page_number=1)
        assert result is None


@pytest.mark.asyncio
async def test_vision_enricher_skips_empty_images():
    """None or empty bytes should return None."""
    from pipeline.enrichers.vision_enricher import VisionEnricher

    with patch.object(VisionEnricher, "__init__", lambda x: None):
        enricher = VisionEnricher()
        assert await enricher.describe_image(None) is None
        assert await enricher.describe_image(b"") is None


@pytest.mark.asyncio
async def test_vision_enricher_caches_results():
    """Same image bytes should return cached result on second call."""
    from pipeline.enrichers.vision_enricher import VisionEnricher, _VISION_CACHE

    # Clear cache before test
    _VISION_CACHE.clear()

    with patch.object(VisionEnricher, "__init__", lambda x: None):
        enricher = VisionEnricher()

        # Mock the API call methods
        enricher._classify = AsyncMock(return_value="chart_or_graph")
        enricher._vision_call = AsyncMock(return_value="A bar chart showing quarterly revenue.")

        image_bytes = b"\x89PNG" + b"\x00" * 2000

        # First call should hit the API
        result1 = await enricher.describe_image(image_bytes, page_number=1)
        assert result1 is not None
        assert "Chart" in result1 or "chart" in result1.lower() or "bar" in result1.lower()

        # Second call with same bytes should hit cache (no API call)
        call_count_before = enricher._classify.call_count
        result2 = await enricher.describe_image(image_bytes, page_number=1)
        assert result2 == result1
        assert enricher._classify.call_count == call_count_before   # No new API call

    # Cleanup
    _VISION_CACHE.clear()


@pytest.mark.asyncio
async def test_vision_enricher_decorative_returns_none():
    """Decorative images should be classified and return None."""
    from pipeline.enrichers.vision_enricher import VisionEnricher, _VISION_CACHE

    _VISION_CACHE.clear()

    with patch.object(VisionEnricher, "__init__", lambda x: None):
        enricher = VisionEnricher()
        enricher._classify = AsyncMock(return_value="decorative")

        image_bytes = b"\x89PNG" + b"\x00" * 2000
        result = await enricher.describe_image(image_bytes, page_number=5)
        assert result is None

    _VISION_CACHE.clear()
